"""Read-only transaction receipts and normalized GenLayer outcomes."""

import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Match genlayer-js 1.1.8 used by genlayer_write.mjs and the deployed Bradbury
# consensus VERSION 2.0.0. Consensus v0.6 reassigns codes 11–13; its table must
# not be mixed with these legacy SDK receipts.
STATUS_CODES = {
    0: "UNINITIALIZED", 1: "PENDING", 2: "PROPOSING", 3: "COMMITTING",
    4: "REVEALING", 5: "ACCEPTED", 6: "UNDETERMINED", 7: "FINALIZED",
    8: "CANCELED", 9: "APPEAL_REVEALING", 10: "APPEAL_COMMITTING",
    11: "READY_TO_FINALIZE", 12: "VALIDATORS_TIMEOUT", 13: "LEADER_TIMEOUT",
    # Legacy-compatible SDK update; this is a nonterminal phase, not success.
    # genlayer-js commit 2af6928e2587091fb33f5f703160c8a160606048.
    14: "LEADER_REVEALING",
}
EXECUTION_CODES = {
    0: "NOT_VOTED", 1: "FINISHED_WITH_RETURN", 2: "FINISHED_WITH_ERROR",
    3: "TIMEOUT", 4: "NONDET_DISAGREE", 5: "DETERMINISTIC_VIOLATION",
}
RESULT_CODES = {
    0: "IDLE", 1: "AGREE", 2: "DISAGREE", 3: "TIMEOUT",
    4: "DETERMINISTIC_VIOLATION", 5: "NO_MAJORITY",
    6: "MAJORITY_AGREE", 7: "MAJORITY_DISAGREE",
}
RESULT_FIELDS = ("resultName", "result_name", "result", "consensus_result")
NEGATIVE_RESULTS = {"NO_MAJORITY", "TIMEOUT", "DETERMINISTIC_VIOLATION",
                    "DISAGREE", "MAJORITY_DISAGREE"}
# Decided outcomes stop the current wait. They are not all finalized: an
# appeal can start another round for the same transaction, so resume refetches it.
TERMINAL = {"ACCEPTED", "FINALIZED", "UNDETERMINED", "CANCELED",
            "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT", "ERROR"}


def _field(receipt, keys, codes, fallback):
    if not isinstance(receipt, dict):
        return fallback
    for key in keys:
        value = receipt.get(key)
        if value is None or value == "":
            continue
        normalized = str(value).strip().upper()
        if normalized.isdigit():
            return codes.get(int(normalized), normalized)
        aliases = {name.replace("_", ""): name for name in codes.values()}
        return aliases.get(normalized.replace("_", ""), normalized)
    return fallback


def _consistent_field(receipt, keys, codes, fallback):
    if not isinstance(receipt, dict):
        return fallback
    values = {_field(receipt, (key,), codes, fallback)
              for key in keys if receipt.get(key) not in (None, "")}
    if not values:
        return fallback
    # Numeric codes and decoded names must describe the same outcome.
    return values.pop() if len(values) == 1 else "INCONSISTENT"


def status_of(receipt):
    return _consistent_field(receipt, ("statusName", "status_name", "status", "consensus_status"),
                             STATUS_CODES, "PENDING")


def execution_of(receipt):
    return _consistent_field(receipt, ("txExecutionResultName", "tx_execution_result_name",
                                      "txExecutionResult", "tx_execution_result"), EXECUTION_CODES, "UNKNOWN")


def consensus_result_of(receipt):
    return _consistent_field(receipt, RESULT_FIELDS, RESULT_CODES, "UNKNOWN")


def finalized_no_execution(receipt):
    """A finalized leader timeout with no execution or consensus decision."""
    return (status_of(receipt) == "FINALIZED" and consensus_result_of(receipt) == "IDLE"
            and execution_of(receipt) == "NOT_VOTED")


def finalized_failure(receipt):
    """An explicit failed final outcome; acknowledging it never implies success."""
    result, execution = consensus_result_of(receipt), execution_of(receipt)
    if (status_of(receipt) != "FINALIZED" or result not in RESULT_CODES.values()
            or execution not in EXECUTION_CODES.values()):
        return False
    return result in NEGATIVE_RESULTS or execution != "FINISHED_WITH_RETURN"


def successful(receipt):
    status = status_of(receipt)
    if status not in {"ACCEPTED", "FINALIZED"} or execution_of(receipt) != "FINISHED_WITH_RETURN":
        return False
    if consensus_result_of(receipt) in {"AGREE", "MAJORITY_AGREE"}:
        return True
    # Older compact ACCEPTED receipts omit result, but ACCEPTED itself records
    # agreement. FINALIZED can also close a failed decision: never infer success
    # there from the leader's successful return or from missing result metadata.
    return status == "ACCEPTED" and all(receipt.get(key) in (None, "") for key in RESULT_FIELDS)


def fetch_receipt(tx, rpc="", timeout=30):
    command = ["node", os.path.join(ROOT, "scripts", "genlayer_write.mjs"), "--receipt", tx]
    if rpc:
        command += ["--rpc", rpc]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return json.loads(result.stdout)
