#!/usr/bin/env python3
"""Drive one live case, one transaction at a time, and write the manifest as
hashes appear.

The manifest line is written the moment the bridge prints a transaction hash,
before anything has settled: record the hash at submit, build the report later.
Re-running any step skips what the manifest already holds, so an interrupted
run continues instead of paying twice.

    python3 scripts/run_case.py open      --address $C --account publisher
    python3 scripts/run_case.py challenge --address $C --claim-id 0 --account challenger
    python3 scripts/run_case.py reveal    --address $C --claim-id 0 --account publisher
    python3 scripts/run_case.py probes    --address $C --challenge-id 0 --account challenger
    python3 scripts/run_case.py admit     --address $C --challenge-id 0 --account challenger
    python3 scripts/run_case.py retry     --address $C --challenge-id 0 --account challenger
    python3 scripts/run_case.py rule      --address $C --challenge-id 0 --account challenger

Add --dry-run to any step to print the invocations without sending them.
Receipt handling is covered by offline regression tests. A live run still
requires a funded account and a public model endpoint.
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cli"))

import impeach as tool  # noqa: E402
from chain_receipts import TERMINAL, consensus_result_of, execution_of, fetch_receipt, finalized_failure, status_of, successful

TX_RE = re.compile(r"Transaction Hash:\s*(0x[0-9a-fA-F]+)")


def load_claim(path: str) -> dict:
    with open(path, encoding="utf-8") as source:
        claim = json.load(source)
    claim["_items"] = tool.load_items(os.path.join(ROOT, claim["items"]))
    return claim


def load_rewrites(claim: dict) -> dict:
    folder = os.path.join(ROOT, claim["rewrites"])
    out = {}
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json"):
            with open(os.path.join(folder, name), encoding="utf-8") as source:
                env = json.load(source)
            problems = tool.validate_envelope(env, claim["_items"][env["item_index"]])
            if problems:
                raise SystemExit("%s: %s" % (name, "; ".join(problems)))
            out[env["item_index"]] = env
    return out


def manifest_rows(path: str) -> dict:
    rows = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    row = json.loads(line)
                    rows[row["key"]] = row
    return rows


class Runner:
    def __init__(self, args):
        self.args = args
        self.rows = manifest_rows(args.manifest)
        self.confirmed = set()
        self.acknowledged = set()
        for row in self.rows.values():
            if row.get("address", "").lower() != args.address.lower():
                raise SystemExit("manifest belongs to a different or unspecified contract; use a separate --manifest for this case")
        os.makedirs(os.path.dirname(os.path.abspath(args.manifest)), exist_ok=True)

    def wait(self, row):
        if row["tx"] in self.confirmed or row["tx"] in self.acknowledged or self.args.dry_run:
            return
        deadline = time.monotonic() + self.args.wait_timeout
        last = "PENDING"
        while True:
            try:
                receipt = fetch_receipt(row["tx"], self.args.rpc,
                                        timeout=max(1, min(30, deadline - time.monotonic())))
                last = "%s / %s / %s" % (status_of(receipt), execution_of(receipt), consensus_result_of(receipt))
                if successful(receipt):
                    self.confirmed.add(row["tx"])
                    print("accepted  %s %s" % (row["key"], row["tx"]), flush=True)
                    return
                failed = status_of(receipt) in {"UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "CANCELED"}
                failed |= finalized_failure(receipt)
                if row["tx"] in getattr(self.args, "acknowledge_failed", []) and failed:
                    self.acknowledged.add(row["tx"])
                    print("acknowledged failure  %s %s (%s); no successful result assumed and no duplicate sent" %
                          (row["key"], row["tx"], last), flush=True)
                    return
                if status_of(receipt) in TERMINAL:
                    raise SystemExit("%s ended %s (%s); inspect the receipt before continuing; no duplicate was sent" %
                                     (row["key"], last, row["tx"]))
            except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                last = "receipt unavailable: %s" % exc
            if time.monotonic() >= deadline:
                raise SystemExit("still waiting for %s: %s; rerun to resume tracking %s" %
                                 (row["key"], last, row["tx"]))
            time.sleep(min(self.args.poll_interval, max(0, deadline - time.monotonic())))

    def resume(self):
        for row in self.rows.values():
            self.wait(row)

    def send(self, key: str, method: str, call_args: list, value: int = 0, extra: dict = None) -> bool:
        """One write. Returns True if it was sent (or would be, in a dry run)."""
        signature = hashlib.sha256(json.dumps([method, call_args, str(value)], ensure_ascii=False,
                                              sort_keys=True).encode()).hexdigest()
        if key in self.rows:
            if self.rows[key].get("signature") != signature:
                raise SystemExit("%s inputs changed; use a separate --manifest for a new case" % key)
            self.wait(self.rows[key])
            print("skip  %s" % key, flush=True)
            return False
        a = self.args
        cmd = ["node", "scripts/genlayer_write.mjs", a.address, method, "--value", str(value)]
        if a.account:
            cmd += ["--account", a.account]
        if a.rpc:
            cmd += ["--rpc", a.rpc]
        # every argument travels as JSON so that long text with newlines and
        # quotes is never re-parsed by a shell
        cmd += ["--args-json", json.dumps(call_args, ensure_ascii=False, separators=(",", ":"))]
        if a.dry_run:
            print(" ".join(shlex.quote(c) for c in cmd), flush=True)
            return True
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode != 0:
            raise SystemExit(result.returncode)
        match = TX_RE.search(result.stdout + result.stderr)
        if not match:
            raise SystemExit("no transaction hash printed for " + key)
        row = {"key": key, "tx": match.group(1), "method": method, "at": int(time.time()),
               "address": a.address, "signature": signature}
        row.update(extra or {})
        with open(a.manifest, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.rows[key] = row
        print("sent  %s %s" % (key, row["tx"]), flush=True)
        self.wait(row)
        if a.delay > 0:
            time.sleep(a.delay)
        return True

    def read(self, method: str, *call_args):
        return tool.chain_call(self.args.address, method, list(call_args), self.args.rpc)


def step_open(r: Runner) -> int:
    claim = load_claim(r.args.claim)
    if "REPLACE-ME" in claim["endpoint"] or "REPLACE-ME" in claim["subject"]:
        raise SystemExit("set subject and endpoint in %s first" % r.args.claim)
    hashes = [tool.item_commitment(it["prompt"], it["answer"], it.get("salt", "")) for it in claim["_items"]]
    r.send(
        "open",
        "open_claim",
        [
            claim["subject"],
            claim["endpoint"],
            str(claim["score_milli"]),
            json.dumps(hashes),
            claim["scoring_rule"],
            json.dumps(claim["prompt_template"], ensure_ascii=False),
            json.dumps(claim["decode_params"]),
            ",".join(claim["classes"]),
            str(claim["delta_threshold"]),
            str(claim["recall_threshold"]),
            str(claim["min_items"]),
            str(claim["bond"]),
            str(claim["stake"]),
            json.dumps(claim["extras"]),
        ],
        value=int(claim["bond"]),
        extra={"step": "open"},
    )
    return 0


def step_challenge(r: Runner) -> int:
    claim = load_claim(r.args.claim)
    subset = list(range(len(claim["_items"])))
    if r.args.subset:
        subset = [int(x) for x in r.args.subset.split(",")]
    r.send(
        "challenge:%d" % r.args.claim_id,
        "challenge",
        [str(r.args.claim_id), json.dumps(subset), json.dumps(claim["classes"])],
        value=int(claim["stake"]) * len(subset),
        extra={"step": "challenge", "claim_id": r.args.claim_id, "subset": subset},
    )
    return 0


def step_reveal(r: Runner) -> int:
    claim = load_claim(r.args.claim)
    payload = json.dumps(
        [{"prompt": it["prompt"], "answer": it["answer"], "salt": it.get("salt", "")} for it in claim["_items"]],
        ensure_ascii=False,
    )
    r.send(
        "reveal:%d" % r.args.claim_id,
        "reveal_items",
        [str(r.args.claim_id), payload],
        extra={"step": "reveal", "claim_id": r.args.claim_id},
    )
    return 0


def _subset(r: Runner) -> list:
    if r.args.dry_run and not r.args.live_reads:
        available = list(range(len(load_claim(r.args.claim)["_items"])))
    else:
        available = r.read("get_challenge", r.args.challenge_id)["subset"]
    if not r.args.subset:
        return available
    picked = [int(x) for x in r.args.subset.split(",")]
    if len(set(picked)) != len(picked) or any(i not in available for i in picked):
        raise SystemExit("--subset must contain distinct indices from the challenged subset")
    return picked


def step_probes(r: Runner) -> int:
    """First pass: the pinned answer, the recall probe and the rewrite for every item."""
    claim = load_claim(r.args.claim)
    rewrites = load_rewrites(claim)
    h = r.args.challenge_id
    for i in _subset(r):
        r.send("probe:%d:%d:PINNED" % (h, i), "probe", [str(h), str(i), "PINNED", ""],
               extra={"step": "probe", "challenge_id": h, "item_index": i, "mode": "PINNED"})
        r.send("probe:%d:%d:RECALL" % (h, i), "probe", [str(h), str(i), "RECALL", ""],
               extra={"step": "probe", "challenge_id": h, "item_index": i, "mode": "RECALL"})
        if i in rewrites:
            env = rewrites[i]
            r.send("probe:%d:%d:REWRITE" % (h, i), "probe", [str(h), str(i), "REWRITE", tool.canonical_envelope(env)],
                   extra={"step": "probe", "challenge_id": h, "item_index": i, "mode": "REWRITE",
                          "rewrite_hash": tool.rewrite_hash(env["class"], env["prompt"], env["answer"])})
    return 0


def step_admit(r: Runner) -> int:
    """Second pass, once the first has settled: referee framing two for every
    rewrite that framing one let through."""
    h = r.args.challenge_id
    waiting = 0
    for i in _subset(r):
        if r.args.dry_run and not r.args.live_reads:
            state = {"stage_c1": "ADMISSIBLE", "stage_c2": "PENDING", "touched": True}
        else:
            state = r.read("get_probe", h, i)
        if not state.get("touched") or state.get("stage_c1") == "PENDING":
            waiting += 1
            continue
        if state["stage_c1"] == "ADMISSIBLE" and state["stage_c2"] == "PENDING":
            r.send("probe:%d:%d:ADMIT" % (h, i), "probe", [str(h), str(i), "ADMIT", ""],
                   extra={"step": "probe", "challenge_id": h, "item_index": i, "mode": "ADMIT"})
    if waiting:
        print("%d rewrites have not settled yet; run this step again later" % waiting)
    return 0


def step_retry(r: Runner) -> int:
    """Ask once more wherever the endpoint did not answer."""
    h = r.args.challenge_id
    if r.args.dry_run and not r.args.live_reads:
        print("retry reads chain state; nothing to print in a dry run without --live-reads")
        return 0
    for i in _subset(r):
        state = r.read("get_probe", h, i)
        if not state.get("touched"):
            continue
        for mode, field in (("PINNED", "pinned"), ("RECALL", "recall"), ("REWRITE", "rewrite")):
            if state.get(field) == "DEAD":
                r.send("retry:%d:%d:%s" % (h, i, mode), "probe", [str(h), str(i), mode, ""],
                       extra={"step": "retry", "challenge_id": h, "item_index": i, "mode": mode})
    return 0


def step_rule(r: Runner) -> int:
    h = r.args.challenge_id
    r.send("rule:%d" % h, "rule", [str(h)], extra={"step": "rule", "challenge_id": h})
    return 0


STEPS = {
    "open": step_open, "challenge": step_challenge, "reveal": step_reveal,
    "probes": step_probes, "admit": step_admit, "retry": step_retry, "rule": step_rule,
}


def main() -> int:
    ap = argparse.ArgumentParser(prog="run_case")
    ap.add_argument("step", choices=sorted(STEPS))
    ap.add_argument("--address", required=True)
    ap.add_argument("--claim", default=os.path.join(ROOT, "calibration", "claim-gsm8k.json"))
    ap.add_argument("--claim-id", type=int, default=0)
    ap.add_argument("--challenge-id", type=int, default=0)
    ap.add_argument("--subset", default="", help="comma separated item indices; default is every item")
    ap.add_argument("--manifest", default=os.path.join(ROOT, "runs", "bradbury.jsonl"))
    ap.add_argument("--account", default="")
    ap.add_argument("--rpc", default="")
    ap.add_argument("--delay", type=float, default=5.0)
    ap.add_argument("--wait-timeout", type=float, default=600, help="seconds to wait for each submitted transaction")
    ap.add_argument("--poll-interval", type=float, default=5, help="seconds between receipt reads")
    ap.add_argument("--acknowledge-failed", action="append", default=[], metavar="TX_HASH",
                    help="after saving and inspecting a decided failure, skip that hash without resubmitting it; repeat per hash")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live-reads", action="store_true", help="in a dry run, still read chain state")
    args = ap.parse_args()
    if args.wait_timeout <= 0 or args.poll_interval <= 0 or args.delay < 0:
        ap.error("wait timeout and poll interval must be positive; delay must be nonnegative")
    runner = Runner(args)
    runner.resume()
    return STEPS[args.step](runner)


if __name__ == "__main__":
    raise SystemExit(main())
