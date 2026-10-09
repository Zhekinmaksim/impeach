#!/usr/bin/env python3
"""Turn a live run into the published snapshot.

Reads the manifest written by scripts/run_case.py, asks the explorer what became
of every transaction, reads the settled state back from the contract, and writes
web/case.json with provenance "bradbury".

    python3 scripts/collect.py runs/bradbury.jsonl --address $CONTRACT --out web/case.json

A probe whose transaction ended UNDETERMINED never wrote state: the validators
could not agree on what the model answered. Those are counted here and carried
into the snapshot rather than dropped, because at temperature 0 that
disagreement is itself a finding about the subject.

Nothing is estimated. If nothing has settled, the old snapshot is left in place
and the exit status is non-zero.

Offline, to test the pipeline without a chain:

    python3 scripts/simulate.py --record /tmp/reads.json --out /tmp/sim.json
    python3 scripts/collect.py test/fixtures/manifest.jsonl --from-json /tmp/reads.json --out /tmp/case.json
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cli"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import impeach as tool  # noqa: E402
import snapshot  # noqa: E402
from chain_receipts import TERMINAL, execution_of, fetch_receipt, status_of

def main() -> int:
    ap = argparse.ArgumentParser(prog="collect")
    ap.add_argument("manifest")
    ap.add_argument("--address", default="")
    ap.add_argument("--rpc", default="")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--from-json", default="", help="recorded reads, for offline runs")
    ap.add_argument("--claims", default="", help="comma separated claim ids; default is every claim")
    ap.add_argument("--items", default=os.path.join(ROOT, "calibration", "gsm8k-24.items.json"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = [json.loads(line) for line in open(args.manifest, encoding="utf-8") if line.strip()]

    if args.from_json:
        recorded = json.load(open(args.from_json, encoding="utf-8"))

        def read(method, *call_args):
            return recorded["reads"][json.dumps([method, list(call_args)])]

        receipts = recorded.get("receipts", {})
    else:
        if not args.address:
            raise SystemExit("--address or --from-json is required")

        def read(method, *call_args):
            return tool.chain_call(args.address, method, list(call_args), args.rpc, args.timeout)

        receipts = {}
        for row in rows:
            try:
                receipts[row["tx"]] = fetch_receipt(row["tx"], args.rpc, args.timeout)
            except Exception as exc:  # Keep unavailable receipts visible as pending.
                print("receipt unavailable for %s: %s" % (row["tx"], exc), file=sys.stderr)
                receipts[row["tx"]] = None

    statuses = {}
    executions = {}
    by_mode = {}
    for row in rows:
        st = status_of(receipts.get(row["tx"]))
        row["status"] = st
        row["execution"] = execution_of(receipts.get(row["tx"]))
        statuses[st] = statuses.get(st, 0) + 1
        executions[row["execution"]] = executions.get(row["execution"], 0) + 1
        if row.get("mode"):
            slot = by_mode.setdefault(row["mode"], {})
            slot[st] = slot.get(st, 0) + 1
    pending = [r["tx"] for r in rows if r["status"] not in TERMINAL]

    counts = read("counts")
    wanted = [int(x) for x in args.claims.split(",")] if args.claims else list(range(counts["claims"]))
    cases = []
    for cid in wanted:
        txs = {}
        for row in rows:
            if row.get("claim_id") == cid or row.get("step") == "open":
                txs[row["key"]] = {"tx": row["tx"], "status": row["status"], "execution": row["execution"]}
        case = snapshot.build_case(read, cid, txs=txs)
        if case["challenge"]:
            hid = case["challenge"]["challenge_id"]
            for row in rows:
                if row.get("challenge_id") == hid:
                    txs[row["key"]] = {"tx": row["tx"], "status": row["status"], "execution": row["execution"]}
        cases.append(case)

    previews = {}
    if os.path.exists(args.items):
        for it in tool.load_items(args.items):
            previews[tool.content_hash(it["prompt"])] = it["prompt"]
    sealed = {}
    for case in cases:
        for it in case["items"]:
            previews[it["content_hash"]] = it["prompt"]
            sealed.setdefault(it["content_hash"], it["item_hash"])
    registry = snapshot.build_registry(read, previews, sealed)

    settled = [c for c in cases if c["claim"]["burned_at"] or c["certificate"]["contested"]]
    print("%d transactions: %s" % (len(rows), ", ".join("%s %d" % kv for kv in sorted(statuses.items()))))
    for mode in sorted(by_mode):
        print("  %-8s %s" % (mode, ", ".join("%s %d" % kv for kv in sorted(by_mode[mode].items()))))
    if pending:
        print("%d still settling, re-run later: %s" % (len(pending), ", ".join(t[:12] for t in pending[:5])))
    if not settled:
        print("Nothing settled. Not writing a snapshot — the old one stays in place.")
        return 2

    snap = snapshot.envelope("bradbury", args.address, cases, registry, int(time.time()))
    snap["receipts"] = {"total": len(rows), "by_status": statuses, "by_execution": executions,
                        "by_mode": by_mode, "pending": len(pending)}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("%d cases, %d registry rows -> %s" % (len(cases), len(registry), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
