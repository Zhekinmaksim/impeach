#!/usr/bin/env python3
"""Run the referee with per-request evidence and conservative OpenRouter caps."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

from local_env import load_local_env, model_key
import referee_dryrun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--cost-cap", type=float, default=0.60)
    parser.add_argument("--total-cost-cap", type=float, default=1.0)
    parser.add_argument("--focused", action="store_true", help="two honest unit rewrites and all four controls")
    parser.add_argument("--claim", default="")
    parser.add_argument("--controls", default="")
    args = parser.parse_args()
    load_local_env()
    os.environ["REFEREE_MODEL"] = args.model
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    base = os.environ["OPENAI_BASE_URL"]
    token = model_key()
    if not token:
        raise SystemExit("OpenRouter credential missing")

    def request(path, body=None, authenticated=True):
        headers = {"content-type": "application/json"}
        if authenticated:
            headers["authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)

    models = request("/models", authenticated=False)["data"]
    model = next(item for item in models if item["id"] == args.model)
    pricing = model["pricing"]
    input_rate = float(pricing["prompt"])
    output_rate = float(pricing["completion"])
    request_rate = float(pricing.get("request", "0"))
    initial_usage = float(request("/key")["data"]["usage"])
    summary = {"model": args.model, "pricing": pricing, "initial_key_usage": initial_usage,
               "cost_cap": args.cost_cap, "total_cost_cap": args.total_cost_cap,
               "focused": args.focused,
               "claim": args.claim or "calibration/claim-gsm8k.json",
               "source_sha256": hashlib.sha256((Path(__file__).resolve().parents[1] / "contracts/impeach.py").read_bytes()).hexdigest(),
               "requests": 0, "cost_usd": 0.0, "completed": False}
    args.transcript.parent.mkdir(parents=True, exist_ok=True)
    if args.transcript.exists():
        raise SystemExit("transcript already exists; choose a new file to preserve past evidence")

    with args.transcript.open("x", encoding="utf-8") as transcript:
        def live_llm(prompt):
            # UTF-8 byte count is a deliberately conservative token upper bound.
            maximum = (len(prompt.encode("utf-8")) + 200) * input_rate + args.max_tokens * output_rate + request_rate
            key_usage = float(request("/key")["data"]["usage"])
            if summary["cost_usd"] + maximum > args.cost_cap or key_usage + maximum > args.total_cost_cap:
                raise SystemExit("referee cost cap reached; no further request sent")
            body = {"model": args.model, "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0, "max_tokens": args.max_tokens}
            if "response_format" in model.get("supported_parameters", []):
                body["response_format"] = {"type": "json_object"}
            if "reasoning" in model.get("supported_parameters", []):
                body["reasoning"] = {"enabled": False}
            data = request("/chat/completions", body)
            usage = data.get("usage", {})
            cost = usage.get("cost")
            if cost is None:
                cost = usage.get("prompt_tokens", len(prompt.encode()) + 200) * input_rate + usage.get("completion_tokens", args.max_tokens) * output_rate + request_rate
            summary["requests"] += 1
            summary["cost_usd"] += float(cost)
            transcript.write(json.dumps({"index": summary["requests"], "at": int(time.time()),
                                         "request": body, "response": data, "usage": usage,
                                         "cost_usd": float(cost)}, ensure_ascii=False) + "\n")
            transcript.flush()
            os.fsync(transcript.fileno())
            return data["choices"][0]["message"]["content"]

        referee_dryrun.live_llm = live_llm
        if args.focused:
            load_corpus = referee_dryrun.pop.load_corpus
            def focused_corpus():
                corpus = load_corpus()
                corpus["rewrites"] = {index: corpus["rewrites"][index] for index in (1, 17)}
                return corpus
            referee_dryrun.pop.load_corpus = focused_corpus
        sys.argv = ["referee_dryrun.py", "--out", str(args.out)]
        if args.claim:
            sys.argv += ["--claim", args.claim, "--controls", args.controls]
        try:
            result = referee_dryrun.main()
            summary["completed"] = True
            summary["gate_passed"] = result == 0
        finally:
            summary["final_key_usage"] = float(request("/key")["data"]["usage"])
            args.transcript.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary), flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
