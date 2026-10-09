"""Read-only transaction receipts and normalized GenLayer outcomes."""

import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_CODES = {
    0: "UNINITIALIZED", 1: "PENDING", 2: "PROPOSING", 3: "COMMITTING",
    4: "REVEALING", 5: "ACCEPTED", 6: "UNDETERMINED", 7: "FINALIZED",
    8: "CANCELED", 9: "APPEALREVEALING", 10: "APPEALCOMMITTING",
    11: "VALIDATORSTIMEOUT", 12: "LEADERTIMEOUT", 13: "LEADERREVEALING",
}
EXECUTION_CODES = {
    0: "NOT_VOTED", 1: "FINISHED_WITH_RETURN", 2: "FINISHED_WITH_ERROR",
    3: "TIMEOUT", 4: "NONDET_DISAGREE", 5: "DETERMINISTIC_VIOLATION",
}
TERMINAL = {"ACCEPTED", "FINALIZED", "UNDETERMINED", "CANCELED",
            "VALIDATORSTIMEOUT", "LEADERTIMEOUT", "ERROR"}


def _field(receipt, keys, codes, fallback):
    if not isinstance(receipt, dict):
        return fallback
    for key in keys:
        value = receipt.get(key)
        if value is None or value == "":
            continue
        if str(value).isdigit():
            return codes.get(int(value), str(value))
        return str(value).upper()
    return fallback


def status_of(receipt):
    return _field(receipt, ("statusName", "status_name", "status", "consensus_status"),
                  STATUS_CODES, "PENDING")


def execution_of(receipt):
    return _field(receipt, ("txExecutionResultName", "tx_execution_result_name",
                           "txExecutionResult", "tx_execution_result"), EXECUTION_CODES, "UNKNOWN")


def successful(receipt):
    return status_of(receipt) in {"ACCEPTED", "FINALIZED"} and execution_of(receipt) == "FINISHED_WITH_RETURN"


def fetch_receipt(tx, rpc="", timeout=30):
    command = ["node", os.path.join(ROOT, "scripts", "genlayer_write.mjs"), "--receipt", tx]
    if rpc:
        command += ["--rpc", rpc]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return json.loads(result.stdout)
