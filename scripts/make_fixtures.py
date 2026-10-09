#!/usr/bin/env python3
"""Write test/fixtures/parity.json: what the Python core computes for a fixed
set of inputs. test/test_parity.mjs holds web/src/seal.js to it, and
test/run_tests.py refuses to pass if the committed file is stale."""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cli"))

import impeach as tool  # noqa: E402

PATH = os.path.join(ROOT, "test", "fixtures", "parity.json")


def build() -> dict:
    items = tool.load_items(os.path.join(ROOT, "calibration", "gsm8k-24.items.json"))
    texts = [it["prompt"] for it in items[:6]] + [
        "  a\tb\u00a0c  ", "“Q” ‘x’", "", "ÀÉ İ ß 𝒳", "x\r\n\r\ny", "MiXeD Case\x0b\x0cend",
    ]
    snap = json.load(open(os.path.join(ROOT, "web", "case.json"), encoding="utf-8"))
    return {
        "texts": [
            {"text": t, "squash": tool.squash(t), "flatten": tool.flatten(t), "content_hash": tool.content_hash(t)}
            for t in texts
        ],
        "commitments": [
            {"prompt": it["prompt"], "answer": it["answer"], "salt": it["salt"],
             "hash": tool.item_commitment(it["prompt"], it["answer"], it["salt"])}
            for it in items[:6]
        ] + [{"prompt": "ü", "answer": "é", "salt": "ß", "hash": tool.item_commitment("ü", "é", "ß")}],
        "verdicts": [
            {
                "terms": {k: c["claim"][k] for k in ("score_milli", "delta_threshold", "recall_threshold", "min_items")},
                "probes": c["probes"],
                "result": tool.rule_offline(
                    {k: c["claim"][k] for k in ("score_milli", "delta_threshold", "recall_threshold", "min_items")},
                    c["probes"],
                ),
            }
            for c in snap["cases"]
        ],
    }


if __name__ == "__main__":
    if "--check" in sys.argv:
        current = json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else None
        if current != build():
            print("test/fixtures/parity.json is stale; run python3 scripts/make_fixtures.py")
            raise SystemExit(1)
        print("fixtures ok")
    else:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(build(), f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("wrote " + PATH)
