#!/usr/bin/env python3
"""Explicitly recover a finalized, unapplied probe; preserve every hash.

This sends a new transaction. It never finalizes or appeals the original, and
never resumes unrelated manifest entries. The existing bridge performs its
normal gas preflight. Use --dry-run to perform all reads without submitting.
The appended previous_receipt path is relative to the manifest's directory.
An interrupted dispatch requires manual reconciliation before another attempt.
One recovery per slot is the default; --max-recoveries permits at most six.
"""

import argparse
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time

import run_case
import native_failure_proof as proof
from chain_receipts import (NEGATIVE_RESULTS, consensus_result_of, execution_of,
                            fetch_receipt, finalized_failure, finalized_no_execution, status_of)
CORE_FIELDS = {"key", "tx", "method", "at", "address", "signature"}
TX = re.compile(r"^0x[0-9a-fA-F]{64}$")
SUBJECT_MODES = ('PINNED', 'RECALL', 'REWRITE')
SUBJECT_DEADLINE_MARGIN = 120
MAX_RECOVERIES = 6


def subject_deadline(args):
    value = getattr(args, 'subject_deadline', None)
    if value is not None and (type(value) is not int or value <= 0):
        raise SystemExit('subject deadline must be a positive integer UTC epoch in seconds')
    return value


def bind_subject_policy(args, row):
    """Standalone recoveries retain an opted-in completer's frozen deadline."""
    path = os.path.abspath(args.manifest) + '.complete/identity.json'
    if not os.path.exists(path):
        return args
    try:
        with open(path, encoding='utf-8') as stream:
            identity = json.load(stream)
    except (OSError, ValueError) as exc:
        raise SystemExit('cannot read frozen completion identity') from exc
    if not isinstance(identity, dict):
        raise SystemExit('invalid frozen completion identity')
    if 'subject_first' not in identity and 'subject_deadline' not in identity:
        return args  # Legacy completion policy has no additional subject guard.
    deadline = identity.get('subject_deadline')
    if identity.get('subject_first') is not True or (deadline is not None and
            (type(deadline) is not int or deadline <= 0)):
        raise SystemExit('invalid frozen subject deadline policy')
    claim = run_case.load_claim(args.claim)
    fingerprint = hashlib.sha256(json.dumps([claim, run_case.load_rewrites(claim)],
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    expected = {'address': args.address.lower(), 'challenge_id': row['challenge_id'],
                'input_sha256': fingerprint, 'subject_first': True, 'subject_deadline': deadline}
    if identity != expected:
        raise SystemExit('frozen subject policy identity differs from recovery inputs')
    requested = subject_deadline(args)
    if requested is not None and requested != deadline:
        raise SystemExit('subject deadline differs from frozen completion policy')
    bound = copy.copy(args)
    bound.subject_deadline = deadline
    return bound


def require_subject_window(args, mode, chain_time):
    """Stop new subject dispatches before API expiry; never cancel sent hashes."""
    deadline = subject_deadline(args)
    if deadline is None or mode not in SUBJECT_MODES:
        return
    if type(chain_time) is not int or chain_time <= 0:
        raise SystemExit('invalid chain clock for subject deadline')
    now = time.time()
    if not isinstance(now, (int, float)) or not 0 < now < float('inf'):
        raise SystemExit('invalid local UTC clock for subject deadline')
    if max(now, chain_time) >= deadline - SUBJECT_DEADLINE_MARGIN:
        raise SystemExit('subject deadline reached or within 120 seconds; no subject dispatch permitted')


def max_recoveries(args):
    limit = getattr(args, "max_recoveries", 1)
    if type(limit) is not int or limit not in range(1, MAX_RECOVERIES + 1):
        raise SystemExit("max recoveries must be an integer from 1 to 6")
    return limit


def retryable_receipt(receipt):
    return (finalized_failure(receipt) and
            (consensus_result_of(receipt) in NEGATIVE_RESULTS or finalized_no_execution(receipt)))


def caller_correction(receipt, row, sender):
    """An explicit correction of a reverted REWRITE sent by a different caller.

    Successful returns, pending calls and same-caller semantic failures remain
    ineligible. The caller must also be checked against the current challenger
    and the unlocked signing account before broadcasting.
    """
    previous = receipt.get('sender')
    return (row.get('mode') == 'REWRITE' and isinstance(sender, str) and
            re.fullmatch(r'0x[0-9a-fA-F]{40}', sender) is not None and
            isinstance(previous, str) and re.fullmatch(r'0x[0-9a-fA-F]{40}', previous) is not None and
            previous.lower() != sender.lower() and status_of(receipt) == 'FINALIZED' and
            execution_of(receipt) == 'FINISHED_WITH_ERROR' and
            consensus_result_of(receipt) == 'MAJORITY_AGREE')


def manifest_history(path):
    history = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as source:
            for line in source:
                if line.strip():
                    row = json.loads(line)
                    history.setdefault(row["key"], []).append(row)
    return history


def recovery_chain(row):
    """Return original through latest; infer ordinals for older one-retry rows."""
    chain, seen = [], set()
    current = row
    while True:
        tx = current.get("tx", "")
        if not isinstance(tx, str) or not TX.fullmatch(tx) or tx.lower() in seen or len(chain) > MAX_RECOVERIES:
            raise SystemExit("invalid recovery history: malformed, repeated or excessive transaction hashes")
        seen.add(tx.lower())
        chain.append(current)
        if "previous_tx" not in current:
            if any(key in current for key in ("previous_row", "previous_receipt", "previous_receipt_sha256")):
                raise SystemExit("invalid recovery history: incomplete previous transaction link")
            break
        previous = current.get("previous_row")
        if not isinstance(previous, dict) or current["previous_tx"] != previous.get("tx"):
            raise SystemExit("invalid recovery history: previous_row does not match previous_tx")
        fields = ("key", "method", "address", "signature", "step", "challenge_id", "item_index", "mode", "rewrite_hash")
        if (any(current.get(key) != previous.get(key) for key in fields) or
                str(current.get("value", "0")) != "0" or str(previous.get("value", "0")) != "0"):
            raise SystemExit("invalid recovery history: original probe inputs changed")
        if not isinstance(current.get("previous_receipt"), str) or not current["previous_receipt"]:
            raise SystemExit("invalid recovery history: missing finalized receipt evidence")
        current = previous
    chain.reverse()
    for ordinal, entry in enumerate(chain):
        recorded = entry.get("recovery_ordinal", ordinal)
        if type(recorded) is not int or recorded != ordinal:
            raise SystemExit("invalid recovery history: recovery ordinal disagrees with transaction chain")
    return chain


def recovery_ordinal(row):
    return len(recovery_chain(row)) - 1


def validate_history(row, manifest, history=None, claim_path=None, source_path=None):
    chain = recovery_chain(row)
    history = manifest_history(manifest) if history is None else history
    if history.get(row["key"]) != chain:
        raise SystemExit("invalid recovery history: original manifest rows are missing or changed")
    base = os.path.dirname(os.path.abspath(manifest))
    folder = os.path.realpath(os.path.abspath(manifest) + ".receipts")
    for entry in chain[1:]:
        relative = entry["previous_receipt"]
        path = os.path.realpath(os.path.join(base, relative))
        if os.path.isabs(relative) or os.path.dirname(path) != folder:
            raise SystemExit("invalid recovery history: receipt evidence is outside the manifest receipts directory")
        try:
            with open(path, "rb") as source:
                raw = source.read()
            receipt = json.loads(raw)
        except (OSError, ValueError) as exc:
            raise SystemExit("invalid recovery history: finalized receipt evidence is missing or malformed") from exc
        digest = entry.get("previous_receipt_sha256")
        if digest is not None and digest != hashlib.sha256(raw).hexdigest():
            raise SystemExit("invalid recovery history: finalized receipt evidence changed or is not retryable")
        corrected_sender = entry.get('previous_rewrite_caller_correction')
        if corrected_sender is not None:
            if (entry.get('previous_failure_basis') or
                    not caller_correction(receipt, entry['previous_row'], corrected_sender)):
                raise SystemExit('invalid recovery history: unproven reverted caller correction')
        elif not retryable_receipt(receipt) or entry.get('previous_failure_basis'):
            try:
                proof.verify_reference(entry, manifest, entry['previous_row'], receipt,
                    original_call(entry['previous_row'], claim_path) if claim_path else None,
                    claim_path, source_path)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise SystemExit('invalid recovery history: unproven finalized failure: ' + str(exc)) from exc
    return len(chain) - 1


@contextmanager
def completion_guard(manifest, held_lock=None):
    """Standalone recovery excludes completion; its internal caller borrows its lock."""
    path = manifest + ".complete.lock"
    if held_lock is not None:
        if held_lock.closed or os.fstat(held_lock.fileno()).st_ino != os.stat(path).st_ino:
            raise SystemExit("completion lock is not held for this manifest")
        fcntl.flock(held_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
        return
    os.makedirs(os.path.dirname(os.path.abspath(manifest)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another completion process holds this manifest lock")
        yield


def original_call(row, claim_path):
    if row.get("method") != "probe" or row.get("step") != "probe":
        raise SystemExit("only an original probe step can be recovered")
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
                and state.get("stage_c2") == "PENDING" and state.get("rewrite") != "DEAD")
    if mode == "REWRITE" and (state.get("rewrite", "") != "" or
                              state.get("stage_c1", "PENDING") != "PENDING" or
                              state.get("stage_c2", "PENDING") != "PENDING"):
        return False
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


def record_dispatch(path, row, receipt_relative, receipt_sha256, ordinal, proof_reference=None):
    """Publish a complete, durable marker without replacing an earlier attempt."""
    folder = os.path.dirname(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                     prefix=".dispatch-", delete=False) as target:
        temporary = target.name
        json.dump({"status": "DISPATCHING", "at": int(time.time()), "previous_tx": row["tx"],
                   "key": row["key"], "address": row["address"], "signature": row["signature"],
                   "previous_receipt": receipt_relative, "previous_receipt_sha256": receipt_sha256,
                   "recovery_ordinal": ordinal, "previous_row": row, **(proof_reference or {})}, target)
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


def retry(args, *, completion_lock=None):
    # Other run_case steps skip an existing key. This lock also prevents two
    # recovery helpers from both removing that key in memory and submitting.
    limit = max_recoveries(args)
    subject_deadline(args)
    with completion_guard(args.manifest, completion_lock), open(args.manifest + ".retry.lock", "a", encoding="utf-8") as lock:
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
        args = bind_subject_policy(args, row)
        history = manifest_history(args.manifest)
        ordinal = validate_history(row, args.manifest, history, args.claim,
                                   getattr(args, 'source', os.path.join(run_case.ROOT, 'build/impeach.py')))
        if ordinal >= limit:
            raise SystemExit("this probe already has a recovery attempt at its configured limit (%d)" % limit)
        marker = dispatch_path(args.manifest, row["tx"])
        if os.path.lexists(marker):
            unresolved_dispatch(marker)
        receipt = fetch_receipt(row["tx"], args.rpc)
        corrected_sender = getattr(args, 'corrected_rewrite_sender', None)
        if corrected_sender is not None and not caller_correction(receipt, row, corrected_sender):
            raise SystemExit('caller correction requires a finalized reverted REWRITE from a different sender')
        needs_proof = not retryable_receipt(receipt) and corrected_sender is None
        if needs_proof and not (getattr(args, 'allow_proven_no_messages', False) and proof.candidate(receipt)):
            raise SystemExit("original transaction must be FINALIZED with an explicit negative consensus result "
                             "or IDLE / NOT_VOTED; unknown or inconsistent fields cannot be retried")
        h, i, mode = row["challenge_id"], row["item_index"], row["mode"]
        challenge = runner.read("get_challenge", h)
        if challenge.get("status") != "TRIAL" or i not in challenge.get("subset", []):
            raise SystemExit("item must still belong to an active TRIAL")
        if corrected_sender is not None:
            if challenge.get('challenger', '').lower() != corrected_sender.lower():
                raise SystemExit('corrected sender must be the frozen challenger')
            args.from_address = corrected_sender
            runner.args.from_address = corrected_sender
        claim = runner.read("get_claim", challenge["claim_id"])
        if corrected_sender is not None:
            proof.frozen_claim(claim, args.claim)
        if runner.read("clock") + getattr(args, "deadline_margin", 0) >= challenge["trial_started_at"] + claim["trial_window_s"]:
            raise SystemExit("trial window has closed")
        state = runner.read("get_probe", h, i)
        if not slot_untouched(state, mode):
            raise SystemExit("probe slot is already applied or not ready; refusing a duplicate")
        proof_reference = None
        if needs_proof:
            proof.require(args.address.lower() == row['address'].lower() and
                          challenge.get('challenge_id') == h and claim.get('claim_id') == challenge['claim_id'] and
                          claim.get('status') == 'TRIAL' and claim.get('active_challenge') == h and
                          state.get('challenge_id') == h and state.get('item_index') == i,
                          'claim/challenge/slot identity differs')
            proof.frozen_claim(claim, args.claim)
            proof_reference = proof.obtain(args, row, receipt, call_args)
            if (runner.read('get_probe', h, i) != state or
                    runner.read('get_challenge', h) != challenge or runner.read('get_claim', challenge['claim_id']) != claim):
                raise SystemExit('contract state changed during proof lookup; no duplicate sent')
            if runner.read('clock') + getattr(args, 'deadline_margin', 0) >= challenge['trial_started_at'] + claim['trial_window_s']:
                raise SystemExit('trial window closed during proof lookup')
        if manifest_history(args.manifest) != history:
            raise SystemExit("manifest changed during recovery checks; rerun to inspect it")
        receipt_path = save_receipt(args.manifest, row["tx"], receipt)
        print("saved original finalized receipt: " + receipt_path, flush=True)
        proof_fields = {'previous_failure_basis', 'previous_finalization_proof', 'previous_finalization_proof_sha256',
                        'previous_rewrite_caller_correction'}
        extra = {key: value for key, value in row.items() if key not in CORE_FIELDS | proof_fields}
        receipt_relative = os.path.relpath(receipt_path, os.path.dirname(os.path.abspath(args.manifest)))
        with open(receipt_path, "rb") as source:
            receipt_sha256 = hashlib.sha256(source.read()).hexdigest()
        extra.update(previous_tx=row["tx"], previous_row=dict(row), previous_receipt=receipt_relative,
                     previous_receipt_sha256=receipt_sha256, recovery_ordinal=ordinal + 1)
        extra.update(proof_reference or {})
        if corrected_sender is not None:
            extra['previous_rewrite_caller_correction'] = corrected_sender
        # Run after proof lookup and all other state reads, immediately before
        # the durable dispatch marker. Existing court/proof checks still apply.
        # This guards handoff to the bridge, not execution of already sent calls.
        if subject_deadline(args) is not None and mode in SUBJECT_MODES:
            require_subject_window(args, mode, runner.read('clock'))
        if not args.dry_run:
            record_dispatch(marker, row, receipt_relative, receipt_sha256, ordinal + 1, proof_reference)
        del runner.rows[row["key"]]
        runner.send(row["key"], "probe", call_args, value=0, extra=extra)
        return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("address", "account", "rpc", "manifest", "tx"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--claim", default=os.path.join(run_case.ROOT, "calibration", "claim-gsm8k.json"))
    parser.add_argument("--wait-timeout", type=float, default=600)
    parser.add_argument("--poll-interval", type=float, default=5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument('--allow-proven-no-messages', action='store_true',
                        help='opt in to exact finalized ambiguous outcomes with a verified Phase event proof')
    parser.add_argument('--source', default=os.path.join(run_case.ROOT, 'build/impeach.py'))
    parser.add_argument("--max-recoveries", type=int, choices=range(1, MAX_RECOVERIES + 1), default=1,
                        help="maximum new recovery transactions per slot, excluding the original (default: 1)")
    parser.add_argument('--subject-deadline', type=int,
                        help='API expiry as a positive UTC epoch; subject dispatch stops 120 seconds earlier')
    parser.add_argument('--corrected-rewrite-sender',
                        help='explicitly correct a finalized reverted REWRITE from a wrong caller; must equal challenger')
    args = parser.parse_args(argv)
    if args.wait_timeout <= 0 or args.poll_interval <= 0:
        parser.error("wait timeout and poll interval must be positive")
    if args.subject_deadline is not None and args.subject_deadline <= 0:
        parser.error('subject deadline must be a positive integer UTC epoch in seconds')
    args.delay = 0
    return args


if __name__ == "__main__":
    raise SystemExit(retry(parse_args()))
