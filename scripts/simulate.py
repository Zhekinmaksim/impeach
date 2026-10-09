#!/usr/bin/env python3
"""Run the three scripted subjects through the court locally and write the
snapshot the page reads.

    python3 scripts/simulate.py --out web/case.json

This is a rehearsal, and the snapshot says so: provenance is "simulation", the
page shows a banner, and `impeach check` warns. Nothing here is evidence for a
submission. It exists so the page, the CLI and the recomputation can be built
and checked before a single transaction is paid for.

Each subject is tried in its own local court. On chain the three could not
share an item set: the first trial would burn it for the other two.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import population as pop  # noqa: E402
import scenarios as S  # noqa: E402
import snapshot  # noqa: E402
from drivers import EPOCH, StubDriver  # noqa: E402

SUBJECTS = (
    ("memoriser", pop.Memoriser, 1000,
     "A lookup table over the sealed set. Swears to a perfect score."),
    ("capable", pop.Capable, 900,
     "Solves the problems, with an honest error rate on old and new wording alike."),
    ("neither", pop.Neither, 900,
     "Cannot do the task and has never seen the items. Swears to 90% anyway."),
)


def main() -> int:
    ap = argparse.ArgumentParser(prog="simulate")
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "case.json"))
    ap.add_argument("--record", default="", help="also record the first court's reads, to test scripts/collect.py offline")
    args = ap.parse_args()

    cases = []
    registry = []
    for name, subject, score, note in SUBJECTS:
        world = pop.World(S.CORPUS)
        d = StubDriver(world)
        url = world.serve("https://%s.invalid/v1/chat/completions" % name, subject(S.CORPUS))
        cid, hid, verdict = S.full_case(d, url, score=score, subject="scripted/%s" % name)
        cases.append(snapshot.build_case(d.view, cid, label=name, note=note))
        if args.record and not registry:
            reads = {}

            def recording(method, *call_args):
                reads[json.dumps([method, list(call_args)])] = d.view(method, *call_args)
                return reads[json.dumps([method, list(call_args)])]

            recording("counts")
            snapshot.build_case(recording, cid)
            snapshot.build_registry(recording)
            json.dump({"reads": reads, "receipts": {
                "0xopen": {"status": "FINALIZED"}, "0xp0": {"status": "ACCEPTED"}, "0xp1": {"status": "UNDETERMINED"},
            }}, open(args.record, "w", encoding="utf-8"), ensure_ascii=False)
        if not registry:
            previews = {S.tool.content_hash(it["prompt"]): it["prompt"] for it in S.ITEMS}
            sealed = {it["content_hash"]: it["item_hash"] for it in cases[-1]["items"]}
            registry = snapshot.build_registry(d.view, previews, sealed)
        print("%-10s %s" % (name, verdict))

    snap = snapshot.envelope(
        "simulation", "", cases, registry, EPOCH,
        "Local rehearsal against scripted subjects. Not a chain record and not evidence.",
    )
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("%d cases, %d registry rows -> %s" % (len(cases), len(registry), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
