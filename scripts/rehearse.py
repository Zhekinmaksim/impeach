#!/usr/bin/env python3
"""Try a real model in the local court before anything is sworn on chain.

    python3 scripts/rehearse.py --endpoint http://localhost:11434/v1/chat/completions --model llama3.1:8b

The contract runs for real, on the local stub, and sends the model exactly the
request bodies it would send from Bradbury: the frozen prompt for each sealed
item, for each rewrite, and the recall probe. What is scripted is everything
that is not the subject: answers are marked by reading the `ANSWER:` line the
prompt template asks for, and the corpus rewrites are taken as admitted.

Use it to learn three things before spending a transaction:

  the score you can honestly swear to   sworn above what the model reproduces
                                        is UNSUPPORTED and costs the bond
  whether the model follows the format  replies with no ANSWER: line are wrong
  what the verdict is likely to be      Δ, R and the verdict the contract gives

It is one endpoint asked once, with one scripted marker. It is not a validator
set and its verdict is a forecast, not a finding.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import population as pop  # noqa: E402
import scenarios as S  # noqa: E402
import snapshot  # noqa: E402
from drivers import EPOCH, StubDriver  # noqa: E402
from run_case import load_claim, load_rewrites  # noqa: E402
from local_env import load_local_env, model_key  # noqa: E402

SEALED_URL = "https://subject.invalid/v1/chat/completions"


def run_rehearsal(claim, model, score, http):
    """Use the live claim's terms; only the endpoint and consensus are local."""
    items = claim["_items"]
    rewrites = load_rewrites(claim)
    world = pop.World({"items": items, "rewrites": rewrites, "controls": []})
    world.http = http
    d = StubDriver(world)
    d.warp(int(time.time()) - EPOCH)
    params = dict(claim["decode_params"], model=model)
    bond, stake = int(claim["bond"]), int(claim["stake"])
    cid = d.call(
        d.addr(1), "open_claim", "local/" + model, SEALED_URL, score,
        json.dumps(S.hashes_of(items)), claim["scoring_rule"],
        json.dumps(claim["prompt_template"]), json.dumps(params),
        ",".join(claim["classes"]), claim["delta_threshold"], claim["recall_threshold"],
        claim["min_items"], bond, stake, json.dumps(claim["extras"]), value=bond,
    )
    subset = list(range(len(items)))
    hid = d.call(d.addr(2), "challenge", cid, json.dumps(subset),
                 json.dumps(claim["classes"]), value=stake * len(subset))
    S.reveal(d, cid, items=items)
    S.run_trial(d, hid, subset=subset, envelopes=rewrites, retries=True)
    verdict = d.call(d.addr(3), "rule", hid)
    return d, cid, verdict, d.view("certificate", cid)


def main() -> int:
    load_local_env()
    ap = argparse.ArgumentParser(prog="rehearse")
    ap.add_argument("--claim", default=os.path.join(ROOT, "calibration", "claim-gsm8k.json"))
    ap.add_argument("--endpoint", required=True, help="OpenAI-shaped chat completions URL; http is fine here")
    ap.add_argument("--model", required=True, help="model name the endpoint expects")
    ap.add_argument("--key", default=model_key(), help="bearer token; prefer OPENAI_API_KEY or OPENROUTER_API_KEY in .env.local")
    ap.add_argument("--score", type=int, default=0, help="score to swear to, per mille; 0 just measures")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--out", default="", help="write a rehearsal snapshot the page can show")
    ap.add_argument("--log", default="", help="append actual endpoint responses and usage as JSONL")
    args = ap.parse_args()
    claim = load_claim(args.claim)

    calls = {"n": 0, "dead": 0, "unformatted": 0}

    def http(url, body):
        calls["n"] += 1
        headers = {"content-type": "application/json"}
        if args.key:
            headers["authorization"] = "Bearer " + args.key
        data = body.encode("utf-8") if isinstance(body, str) else body
        if urlparse(args.endpoint).hostname == "openrouter.ai" and os.environ.get("OPENROUTER_PROVIDER"):
            routed = json.loads(data)
            routed["provider"] = {"only": [os.environ["OPENROUTER_PROVIDER"]],
                                  "allow_fallbacks": False, "require_parameters": True}
            data = json.dumps(routed).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(args.endpoint, data=data, headers=headers), timeout=args.timeout) as r:
                payload = r.read()
                if args.log:
                    os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
                    with open(args.log, "a", encoding="utf-8") as log:
                        log.write(json.dumps({"at": int(time.time()), "request": json.loads(data),
                                              "response": json.loads(payload)}, ensure_ascii=False) + "\n")
                try:
                    text = json.loads(payload)["choices"][0]["message"]["content"]
                    if "ANSWER:" not in text and not json.loads(data)["messages"][-1]["content"].startswith(pop.RECALL_INSTRUCTION):
                        calls["unformatted"] += 1
                except Exception:  # noqa: BLE001
                    pass
                sys.stderr.write(".")
                sys.stderr.flush()
                return (r.status, payload)
        except urllib.error.HTTPError as exc:
            calls["dead"] += 1
            return (exc.code, b"")
        except Exception:  # noqa: BLE001
            calls["dead"] += 1
            return (599, b"")

    d, cid, verdict, cert = run_rehearsal(claim, args.model, args.score, http)
    sys.stderr.write("\n")

    print("model                 %s" % args.model)
    print("requests              %d  (%d got no reply)" % (calls["n"], calls["dead"]))
    print("answered as sealed    %d‰" % cert["pinned_milli"])
    print("answered as rewritten %d‰" % cert["rewrite_milli"])
    print("gap Δ                 %d‰   threshold %d‰" % (cert["delta_milli"], claim["delta_threshold"]))
    print("verbatim recall R     %d‰   threshold %d‰" % (cert["recall_milli"], claim["recall_threshold"]))
    print("old answers given     %d" % cert["stale_answers"])
    print("replies without an ANSWER: line  %d" % calls["unformatted"])
    print("forecast              %s %s" % (verdict, cert["reason"]))
    if args.score == 0:
        print("\nThe measured sealed score is %d‰. Sworn %d‰ or more above what" % (cert["pinned_milli"], claim["delta_threshold"]))
        print("the model reproduces, the verdict is UNSUPPORTED and the bond is lost.")
    if calls["unformatted"]:
        print("\nSome replies had no ANSWER: line and were marked wrong here. On chain a")
        print("language model does the marking and may be more forgiving, or less.")

    if args.out:
        case = snapshot.build_case(d.view, cid, label=args.model, note="Local rehearsal against a real endpoint.")
        previews = {S.tool.content_hash(it["prompt"]): it["prompt"] for it in claim["_items"]}
        sealed = {it["content_hash"]: it["item_hash"] for it in case["items"]}
        snap = snapshot.envelope(
            "simulation", "", [case], snapshot.build_registry(d.view, previews, sealed), int(time.time()),
            "Local rehearsal: a real endpoint, a scripted marker and referee. Not a chain record.",
        )
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("\nsnapshot -> " + args.out)
    return 1 if calls["dead"] or calls["unformatted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
