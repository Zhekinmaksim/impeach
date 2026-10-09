#!/usr/bin/env python3
"""A trial-only OpenRouter gateway with a persistent, conservative spend cap."""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_CEILING
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from local_env import load_local_env

ROOT = Path(__file__).resolve().parent.parent
CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_BODY = 24 * 1024
MAX_REPLY = 256 * 1024
PRICE_CAP = {"prompt": 0.05, "completion": 0.10, "request": 0}  # USD per million tokens; no request fee
MIN_RESERVATION = 1000  # $0.001, never refunded, even if the request fails
RECALL_INSTRUCTION = ("Continue the text below exactly from where it stops. "
                      "Output only the continuation, with no preamble.\n\n")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def trial_requests(model):
    claim = json.loads((ROOT / "calibration/claim-gsm8k.json").read_text())
    if claim["items"] != "calibration/gsm8k-24.items.json" or claim["rewrites"] != "examples/rewrites":
        raise ValueError("Only the committed demonstration corpus is supported")
    items = json.loads((ROOT / claim["items"]).read_text())["items"]
    rewrites = [json.loads(path.read_text()) for path in sorted((ROOT / claim["rewrites"]).glob("*.json"))]
    if len(items) != 24 or len(rewrites) != 24 or {r["item_index"] for r in rewrites} != set(range(24)):
        raise ValueError("Incomplete demonstration corpus")
    params = {key: claim["decode_params"][key] for key in ("temperature", "top_p", "max_tokens", "seed")
              if key in claim["decode_params"]}
    if type(params.get("max_tokens")) is not int or not 1 <= params["max_tokens"] <= 4096:
        raise ValueError("Unsafe max_tokens")
    template = claim["prompt_template"]

    def answer(prompt):
        messages = ([{"role": "system", "content": template["system"]}] if template.get("system") else [])
        messages.append({"role": "user", "content": template["user"].replace("{{item}}", prompt)})
        return dict(params, model=model, messages=messages)

    requests = [answer(item["prompt"]) for item in items] + [answer(item["prompt"]) for item in rewrites]
    for item in items:
        prefix = item["prompt"][:len(item["prompt"]) * claim["extras"]["recall_prefix_milli"] // 1000]
        requests.append(dict(params, model=model, messages=[{"role": "user", "content": RECALL_INSTRUCTION + prefix}], max_tokens=512))
    return requests


def reservation_micros(body):
    # UTF-8 bytes upper-bound the subject tokenizer's input tokens. An additional
    # 1024 tokens covers framing; the price ceiling is also enforced by OpenRouter.
    input_bound = len(canonical(body).encode("utf8")) + 1024
    reserve = (Decimal(input_bound) * Decimal("0.05") + Decimal(body["max_tokens"]) * Decimal("0.10")) * Decimal("1.10")
    return max(MIN_RESERVATION, int(reserve.to_integral_value(rounding=ROUND_CEILING)))


class BudgetLedger:
    """Reserve before the HTTP call in a SQLite write transaction; never refund."""
    def __init__(self, path, budget, identity):
        self.path = str(path)
        amount = Decimal(str(budget)) * 1_000_000
        if not amount.is_finite() or amount <= 0 or amount > 5_000_000 or amount != amount.to_integral_value():
            raise ValueError("Budget must be positive, at most $5, with at most six decimal places")
        self.budget = int(amount)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS settings (
              id INTEGER PRIMARY KEY CHECK (id = 1), budget INTEGER NOT NULL, identity TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS reservations (
              id INTEGER PRIMARY KEY, micros INTEGER NOT NULL CHECK (micros > 0), created INTEGER NOT NULL);""")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT budget, identity FROM settings WHERE id=1").fetchone()
            if row is None:
                db.execute("INSERT INTO settings VALUES (1, ?, ?)", (self.budget, identity))
            elif row != (self.budget, identity):
                raise ValueError("Existing ledger has different budget or trial; do not reset it")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, micros):
        if type(micros) is not int or micros <= 0:
            raise ValueError("Invalid reservation")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT COALESCE(SUM(micros), 0) FROM reservations").fetchone()[0]
            if spent + micros > self.budget:
                return False
            db.execute("INSERT INTO reservations(micros,created) VALUES (?,?)", (micros, int(time.time())))
            return True

    def remaining(self):
        with self.connect() as db:
            spent = db.execute("SELECT COALESCE(SUM(micros),0) FROM reservations").fetchone()[0]
        return self.budget - spent


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the key to another URL.


def upstream_request(key, body):
    request = urllib.request.Request(CHAT_URL, data=canonical(body).encode("utf8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=45) as reply:
        payload = reply.read(MAX_REPLY + 1)
        if len(payload) > MAX_REPLY:
            raise ValueError("Upstream reply too large")
        return reply.status, payload


def error(code, status):
    return status, canonical({"error": {"code": code}}).encode()


class Gateway:
    def __init__(self, model, provider, key, budget, ledger_path, upstream=upstream_request):
        if not model or not provider or not key:
            raise ValueError("Model, provider and key are required")
        self.model, self.provider, self.key = model, provider, key
        self.allowed = {canonical(body) for body in trial_requests(model)}
        self.routing = {"only": [provider], "allow_fallbacks": False, "require_parameters": True, "max_price": PRICE_CAP}
        identity = hashlib.sha256(canonical([sorted(self.allowed), self.routing]).encode()).hexdigest()
        self.ledger = BudgetLedger(ledger_path, budget, identity)
        self.upstream = upstream

    def complete(self, raw):
        if len(raw) > MAX_BODY:
            return error("body_too_large", 413)
        try:
            body = json.loads(raw)
            # Strict canonical matching rejects additional fields, prompt edits,
            # alternate models, changed decoding, streams, tools and extra turns.
            if canonical(body) not in self.allowed:
                return error("request_not_in_trial", 403)
        except (ValueError, TypeError, RecursionError):
            return error("invalid_json", 400)
        try:
            if not self.ledger.reserve(reservation_micros(body)):
                return error("trial_budget_exhausted", 503)
        except sqlite3.Error:
            return error("budget_ledger_unavailable", 503)
        try:
            status, payload = self.upstream(self.key, dict(body, provider=self.routing))
            if status != 200:
                return error("upstream_unavailable", 429 if status == 429 else 502)
            if len(payload) > MAX_REPLY:
                return error("invalid_upstream_response", 502)
            completion = json.loads(payload)
            if completion.get("error") or completion["choices"][0].get("error") or not isinstance(completion["choices"][0]["message"]["content"], str):
                return error("invalid_upstream_response", 502)
            return 200, payload  # Actual model bytes; no repair, retry or cache.
        except urllib.error.HTTPError as exc:
            return error("upstream_unavailable", 429 if exc.code == 429 else 502)
        except TimeoutError:
            return error("upstream_timeout", 504)
        except Exception:
            return error("upstream_unavailable", 502)  # Never expose errors or the key.


def make_handler(gateway):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(50)

        def send(self, status, payload):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path not in ("/health", "/v1/chat/completions"):
                return self.send(*error("not_found", 404))
            remaining = gateway.ledger.remaining()
            self.send(200, canonical({"service": "impeach-local-openrouter", "enabled": remaining >= MIN_RESERVATION,
                "model": gateway.model, "provider": gateway.provider, "allowed_requests": len(gateway.allowed),
                "remaining_reserved_budget_usd": remaining / 1_000_000}).encode())

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                return self.send(*error("not_found", 404))
            if self.headers.get_content_type() != "application/json":
                return self.send(*error("json_required", 415))
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                return self.send(*error("body_too_large", 413))
            raw = self.rfile.read(length)
            if len(raw) != length:
                return self.send(*error("invalid_body", 400))
            self.send(*gateway.complete(raw))

        def log_message(self, fmt, *args):
            # Never log incoming URLs, request bodies, headers or provider errors.
            sys.stderr.write("gateway request completed\n")
    return Handler


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", required=True, help="Allocated remaining USD; at most 5, persisted in the ledger")
    parser.add_argument("--ledger", default=str(ROOT / "runs/openrouter-budget.sqlite"))
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    try:
        gateway = Gateway(os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct"),
            os.environ.get("OPENROUTER_PROVIDER", "deepinfra/fp8"), os.environ.get("OPENROUTER_API_KEY", ""),
            args.budget, args.ledger)
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(gateway))
    except (ValueError, OSError, sqlite3.Error):
        parser.exit(1, "Gateway configuration or ledger invalid; verify settings without resetting the ledger.\n")
    print("Gateway listening on http://127.0.0.1:%d/v1/chat/completions (pid %d)" % (args.port, os.getpid()), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
