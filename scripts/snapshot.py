"""Build the published snapshot. One shape, two sources.

`read(method, *args)` is any callable that returns what the contract view of
that name returns: the local harness in scripts/simulate.py, or `genlayer call`
in scripts/collect.py. The page and `impeach recompute` only ever see this shape,
so a simulated snapshot and a chain snapshot cannot drift apart silently.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cli"))

import impeach as tool  # noqa: E402

FORMAT = "impeach-case/1"


def build_case(read, claim_id: int, label: str = "", note: str = "", txs: dict = None) -> dict:
    claim = read("get_claim", claim_id)
    cert = read("certificate", claim_id)
    case = {
        "label": label or claim["subject"],
        "note": note,
        "claim": claim,
        "certificate": cert,
        "challenge": None,
        "items": [],
        "probes": [],
        "txs": txs or {},
    }
    if claim["burned_at"]:
        for i in range(len(claim["item_hashes"])):
            item = read("get_item", claim_id, i)
            prefix, tail = tool.split_for_recall(item["prompt"], claim["recall_prefix_milli"])
            item["item_hash"] = claim["item_hashes"][i]
            item["recall_prefix"] = prefix
            item["recall_tail"] = tail
            case["items"].append(item)
    if cert["challenge_id"] >= 0:
        ch = read("get_challenge", cert["challenge_id"])
        case["challenge"] = ch
        for i in ch["subset"]:
            case["probes"].append(read("get_probe", ch["challenge_id"], i))
    return case


def build_registry(read, previews: dict = None, sealed: dict = None) -> list:
    rows = []
    offset = 0
    while True:
        page = read("registry", offset, 100)
        rows.extend(page["rows"])
        offset += len(page["rows"])
        if not page["rows"] or offset >= page["total"]:
            break
    for row in rows:
        row["preview"] = (previews or {}).get(row["content_hash"], "")
        if sealed and row["content_hash"] in sealed:
            row["item_hash"] = sealed[row["content_hash"]]
    return rows


def envelope(provenance: str, contract: str, cases: list, registry: list, generated_at: int, note: str = "") -> dict:
    return {
        "format": FORMAT,
        "provenance": provenance,
        "contract": contract,
        "generated_at": generated_at,
        "note": note,
        "cases": cases,
        "registry": registry,
    }
