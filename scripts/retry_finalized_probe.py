#!/usr/bin/env python3
"""Explicitly retry one finalized, unapplied probe once; preserve both hashes.

This sends a new transaction. It never finalizes or appeals the original, and
never resumes unrelated manifest entries. The existing bridge performs its
normal gas preflight. Use --dry-run to perform all reads without submitting.
The appended previous_receipt path is relative to the manifest's directory.
An interrupted dispatch requires manual reconciliation before another attempt.
"""

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
import time

import run_case
from chain_receipts import NEGATIVE_RESULTS, consensus_result_of, fetch_receipt, finalized_failure, finalized_no_execution
CORE_FIELDS = {"key", "tx", "method", "at", "address", "signature"}


def original_call(row, claim_path):
    if row.get("method") != "probe" or row.get("step") != "probe":
        raise SystemExit("only an original probe step can be recovered")
    if "previous_tx" in row:
        raise SystemExit("this probe already has a recovery attempt")
    if str(row.get("value", "0")) != "0":
        raise SystemExit("only a zero-value probe can be recovered")
    h, i, mode = row.get("challenge_id"), row.get("item_index"), row.get("mode")
    if (type(h) is not int or type(i) is not int or h < 0 or i < 0 or
            mode not in {"PINNED", "RECALL", "REWRITE", "ADMIT"} or
            row.get("key") != "probe:%d:%d:%s" % (h, i, mode)):
        raise SystemExit("probe metadata does not identify the original call")
    claim = run_case.load_claim(claim_path)
    if i >= len(claim["_items"]):
        raise SystemExit("item index is outside the current claim")
    payload = ""
    if mode == "REWRITE":
        rewrites = run_case.load_rewrites(claim)
        if i not in rewrites:
            raise SystemExit("the original rewrite is missing from the current claim")
        payload = run_case.tool.canonical_envelope(rewrites[i])
    call_args = [str(h), str(i), mode, payload]
    signature = hashlib.sha256(json.dumps(["probe", call_args, "0"], ensure_ascii=False,
                                         sort_keys=True).encode()).hexdigest()
    if row.get("signature") != signature:
        raise SystemExit("original inputs changed or were nonzero; signature does not match")
    return call_args


def slot_untouched(state, mode):
    if mode == "ADMIT":
        return (state.get("touched") is True and state.get("stage_c1") == "ADMISSIBLE"
                and state.get("stage_c2") == "PENDING")
    field = {"PINNED": "pinned", "RECALL": "recall", "REWRITE": "rewrite_class"}[mode]
    return ((state.get("touched") is False and state.get(field, "") == "") or
            (state.get("touched") is True and state.get(field) == ""))


def save_receipt(manifest, tx, receipt):
    folder = os.path.abspath(manifest) + ".receipts"
    os.makedirs(folder, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                     prefix=tx + ".finalized-", suffix=".json", delete=False) as target:
        json.dump(receipt, target, ensure_ascii=False, indent=2)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
        return target.name


def dispatch_path(manifest, tx):
    return os.path.join(os.path.abspath(manifest) + ".receipts", tx.lower() + ".dispatch.json")


def unresolved_dispatch(path):
    raise SystemExit("recovery dispatch already recorded; reconcile its on-chain outcome and manifest "
                     "before another attempt; no duplicate sent: " + path)


def record_dispatch(path, row, receipt_relative):
    """Publish a complete, durable marker without replacing an earlier attempt."""
    folder = os.path.dirname(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                     prefix=".dispatch-", delete=False) as target:
        temporary = target.name
        json.dump({"status": "DISPATCHING", "at": int(time.time()), "previous_tx": row["tx"],
                   "key": row["key"], "address": row["address"], "signature": row["signature"],
                   "previous_receipt": receipt_relative}, target)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            unresolved_dispatch(path)
        # Also persist the receipts directory entry if this recovery created it.
        for directory_path in (folder, os.path.dirname(folder)):
            directory = os.open(directory_path, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        os.unlink(temporary)


def retry(args):
    # Other run_case steps skip an existing key. This lock also prevents two
    # recovery helpers from both removing that key in memory and submitting.
    with open(args.manifest + ".retry.lock", "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another recovery is using this manifest")
        runner = run_case.Runner(args)
        matches = [row for row in runner.rows.values() if row.get("tx", "").lower() == args.tx.lower()]
        if len(matches) != 1:
            raise SystemExit("--tx must be the latest manifest row for exactly one probe key")
        row = matches[0]
        call_args = original_call(row, args.claim)
        marker = dispatch_path(args.manifest, row["tx"])
        if os.path.lexists(marker):
            unresolved_dispatch(marker)
        receipt = fetch_receipt(row["tx"], args.rpc)
        retryable = (consensus_result_of(receipt) in NEGATIVE_RESULTS or finalized_no_execution(receipt))
        if not finalized_failure(receipt) or not retryable:
            raise SystemExit("original transaction must be FINALIZED with an explicit negative consensus result "
                             "or IDLE / NOT_VOTED; unknown or inconsistent fields cannot be retried")
        h, i, mode = row["challenge_id"], row["item_index"], row["mode"]
        challenge = runner.read("get_challenge", h)
        if challenge.get("status") != "TRIAL" or i not in challenge.get("subset", []):
            raise SystemExit("item must still belong to an active TRIAL")
        claim = runner.read("get_claim", challenge["claim_id"])
        if runner.read("clock") > challenge["trial_started_at"] + claim["trial_window_s"]:
            raise SystemExit("trial window has closed")
        if not slot_untouched(runner.read("get_probe", h, i), mode):
            raise SystemExit("probe slot is already applied or not ready; refusing a duplicate")
        if run_case.manifest_rows(args.manifest).get(row["key"]) != row:
            raise SystemExit("manifest changed during recovery checks; rerun to inspect it")
        receipt_path = save_receipt(args.manifest, row["tx"], receipt)
        print("saved original finalized receipt: " + receipt_path, flush=True)
        extra = {key: value for key, value in row.items() if key not in CORE_FIELDS}
        receipt_relative = os.path.relpath(receipt_path, os.path.dirname(os.path.abspath(args.manifest)))
        extra.update(previous_tx=row["tx"], previous_row=dict(row), previous_receipt=receipt_relative)
        if not args.dry_run:
            record_dispatch(marker, row, receipt_relative)
        del runner.rows[row["key"]]
        runner.send(row["key"], "probe", call_args, value=0, extra=extra)
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("address", "account", "rpc", "manifest", "tx"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--claim", default=os.path.join(run_case.ROOT, "calibration", "claim-gsm8k.json"))
    parser.add_argument("--wait-timeout", type=float, default=600)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.wait_timeout <= 0 or args.poll_interval <= 0:
        parser.error("wait timeout and poll interval must be positive")
    args.delay = 0
    return retry(args)


if __name__ == "__main__":
    raise SystemExit(main())
