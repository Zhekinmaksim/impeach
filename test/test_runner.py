"""Regression checks for the live runner; no wallet or network is used."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import run_case
import chain_receipts


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.args = SimpleNamespace(
            address="0x" + "1" * 40, manifest=os.path.join(self.tmp.name, "case.jsonl"),
            account="", rpc="", delay=0, dry_run=False, live_reads=False,
            wait_timeout=0.05, poll_interval=0.001, subset="", challenge_id=0,
            claim=os.path.join(ROOT, "calibration", "claim-gsm8k.json"),
        )
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_smoke_subset_sends_only_three_probes(self):
        self.args.dry_run = True
        self.args.subset = "0"
        with open(os.path.join(ROOT, "calibration", "gsm8k-24.items.json")) as source:
            items = json.load(source)
        if isinstance(items, dict):
            items = items["items"]
        with patch.object(run_case.tool, "load_items", return_value=items):
            run_case.step_probes(run_case.Runner(self.args))
        lines = self.output.getvalue().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(all("--args-json" in line for line in lines))

    def test_read_recovers_from_transient_rpc_failures_without_a_write(self):
        runner = run_case.Runner(self.args)
        expected = {"pinned": "RIGHT"}
        with patch.object(run_case.tool, "chain_call", side_effect=[
                subprocess.TimeoutExpired("read", 20), RuntimeError("RPC unavailable"), expected]) as read, \
                patch.object(run_case.time, "sleep") as sleep, \
                patch.object(runner, "send") as send:
            self.assertEqual(runner.read("get_probe", 0, 1), expected)
            self.assertEqual(read.call_count, 3)
            for call in read.call_args_list:
                self.assertEqual(call.args, (self.args.address, "get_probe", [0, 1], self.args.rpc))
                self.assertEqual(call.kwargs, {"timeout": 20})
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
            send.assert_not_called()

    def test_read_stops_after_three_failed_attempts(self):
        runner = run_case.Runner(self.args)
        with patch.object(run_case.tool, "chain_call", side_effect=RuntimeError("RPC unavailable")) as read, \
                patch.object(run_case.time, "sleep"), patch.object(runner, "send") as send:
            with self.assertRaisesRegex(RuntimeError, "RPC unavailable"):
                runner.read("counts")
            self.assertEqual(read.call_count, 3)
            send.assert_not_called()

    def test_malformed_read_is_not_retried_or_assumed_successful(self):
        runner = run_case.Runner(self.args)
        with patch.object(run_case.tool, "chain_call", side_effect=json.JSONDecodeError("bad", "", 0)) as read:
            with self.assertRaises(json.JSONDecodeError):
                runner.read("counts")
            self.assertEqual(read.call_count, 1)

    def test_live_subset_must_belong_to_challenge(self):
        runner = run_case.Runner(self.args)
        self.args.subset = "2"
        with patch.object(runner, "read", return_value={"subset": [0, 1]}):
            with self.assertRaisesRegex(SystemExit, "challenged subset"):
                run_case._subset(runner)

    def test_persist_then_wait_and_resume_without_duplicate(self):
        runner = run_case.Runner(self.args)
        sent = subprocess.CompletedProcess([], 0, "Transaction Hash: 0xabc\n", "")
        accepted = {"status": 5, "txExecutionResult": 1}

        def receipt(*args, **kwargs):
            with open(self.args.manifest) as source:
                self.assertEqual(json.loads(source.read())["tx"], "0xabc")
            return accepted

        with patch.object(run_case.subprocess, "run", return_value=sent) as write:
            with patch.object(run_case, "fetch_receipt", side_effect=receipt):
                self.assertTrue(runner.send("open", "open_claim", ["subject"], 100))
                resumed = run_case.Runner(self.args)
                resumed.resume()
                self.assertFalse(resumed.send("open", "open_claim", ["subject"], 100))
            self.assertEqual(write.call_count, 1)

    def test_accepted_contract_error_stops_progress(self):
        runner = run_case.Runner(self.args)
        with patch.object(run_case, "fetch_receipt", return_value={"status": 5, "txExecutionResult": 2}):
            with self.assertRaisesRegex(SystemExit, "FINISHED_WITH_ERROR"):
                runner.wait({"key": "open", "tx": "0xabc"})

    def test_timeout_keeps_hash_for_resume(self):
        runner = run_case.Runner(self.args)
        sent = subprocess.CompletedProcess([], 0, "Transaction Hash: 0xabc\n", "")
        with patch.object(run_case.subprocess, "run", return_value=sent):
            with patch.object(run_case, "fetch_receipt", return_value={"status": 1}):
                with self.assertRaisesRegex(SystemExit, "rerun to resume"):
                    runner.send("open", "open_claim", [], 100)
        self.assertEqual(run_case.manifest_rows(self.args.manifest)["open"]["tx"], "0xabc")

    def test_manifest_cannot_be_reused_for_another_contract(self):
        with open(self.args.manifest, "w") as target:
            target.write(json.dumps({"key": "open", "tx": "0xabc", "address": "0xother"}) + "\n")
        with self.assertRaisesRegex(SystemExit, "different or unspecified contract"):
            run_case.Runner(self.args)

    def test_changed_inputs_do_not_silently_skip_the_old_claim(self):
        runner = run_case.Runner(self.args)
        runner.rows["open"] = {"tx": "0xabc", "signature": "old-inputs"}
        with self.assertRaisesRegex(SystemExit, "inputs changed"):
            runner.send("open", "open_claim", ["new subject"], 100)

    def test_receipts_distinguish_consensus_from_execution(self):
        self.assertEqual(chain_receipts.status_of({"status": 7}), "FINALIZED")
        self.assertEqual(chain_receipts.status_of({"status": 5, "statusName": "Accepted"}), "ACCEPTED")
        self.assertFalse(chain_receipts.successful({"status": 5, "txExecutionResult": 2}))
        self.assertTrue(chain_receipts.successful({"status": 7, "txExecutionResult": 1, "result": 1}))

    def test_finalization_does_not_turn_a_failed_consensus_into_success(self):
        for result in (0, 2, 3, 4, 5, 6, 7, "NO_MAJORITY", "MajorityDisagree", "future_result"):
            with self.subTest(result=result):
                self.assertFalse(chain_receipts.successful({"status": 7, "txExecutionResult": 1, "result": result}))
        self.assertFalse(chain_receipts.successful({"status": 7, "txExecutionResult": 1}))
        self.assertFalse(chain_receipts.successful({"status": 5, "txExecutionResult": 1, "result": 5}))
        self.assertTrue(chain_receipts.successful({"status": 5, "txExecutionResult": 1}))
        self.assertTrue(chain_receipts.successful({"statusName": "Finalized", "txExecutionResultName": "FinishedWithReturn",
                                                  "result": 1, "resultName": "MajorityAgree"}))
        contradictory = {"status": 7, "txExecutionResult": 1, "result": 5, "resultName": "AGREE"}
        self.assertEqual(chain_receipts.consensus_result_of(contradictory), "INCONSISTENT")
        self.assertFalse(chain_receipts.successful(contradictory))

    def test_deployed_result_aliases_are_canonical_without_mutating_raw_evidence(self):
        for code, legacy, canonical in ((1, "AGREE", "MAJORITY_AGREE"),
                                        (2, "DISAGREE", "MAJORITY_DISAGREE"),
                                        (3, "TIMEOUT", "MAJORITY_TIMEOUT")):
            with self.subTest(code=code):
                receipt = {"status": 7, "result": code, "resultName": legacy,
                           "consensus_result": canonical, "txExecutionResult": 1,
                           "lastRound": {"validatorVotes": [0, 4, 3, 3, 1],
                                         "validatorVotesName": ["NOT_VOTED", "DETERMINISTIC_VIOLATION",
                                                                "TIMEOUT", "TIMEOUT", "AGREE"]}}
                raw = json.dumps(receipt)
                self.assertEqual(chain_receipts.consensus_result_of(receipt), canonical)
                self.assertEqual(chain_receipts.successful(receipt), code == 1)
                self.assertEqual(chain_receipts.finalized_failure(receipt), code != 1)
                self.assertEqual(json.dumps(receipt), raw)
                self.assertEqual(chain_receipts.consensus_result_of({"resultName": legacy.lower()}), canonical)
                self.assertEqual(chain_receipts.consensus_result_of({"result_name": canonical.replace("_", "")}),
                                 canonical)

    def test_execution_and_consensus_code_four_have_distinct_meanings(self):
        receipt = {"status": 7, "result": 4, "resultName": "DeterministicViolation",
                   "txExecutionResult": 4, "txExecutionResultName": "NondetDisagree"}
        self.assertEqual(chain_receipts.execution_of(receipt), "NONDET_DISAGREE")
        self.assertEqual(chain_receipts.consensus_result_of(receipt), "DETERMINISTIC_VIOLATION")
        self.assertTrue(chain_receipts.finalized_failure(receipt))
        self.assertFalse(chain_receipts.successful(receipt))
        receipt["txExecutionResultName"] = "DETERMINISTIC_VIOLATION"
        self.assertEqual(chain_receipts.execution_of(receipt), "INCONSISTENT")
        self.assertFalse(chain_receipts.finalized_failure(receipt))

    def test_aliases_do_not_hide_genuine_result_conflicts(self):
        for receipt in ({"result": 1, "resultName": "DISAGREE"},
                        {"result": 3, "resultName": "AGREE"},
                        {"resultName": "AGREE", "consensus_result": "MAJORITY_DISAGREE"}):
            with self.subTest(receipt=receipt):
                self.assertEqual(chain_receipts.consensus_result_of(receipt), "INCONSISTENT")

    def test_recorded_bradbury_consensus_and_execution_combinations(self):
        # Relevant fields copied from the preserved live receipts. Agreement on
        # a contract error and a returned leader proposal without a majority are
        # both failures; the accepted rewrite remains successful.
        examples = [
            ("deploy-receipt.json", {"status": 5, "result": 1, "resultName": "AGREE", "txExecutionResult": 2}, False),
            ("vercel-first-rewrite-receipt.json", {"status": 5, "result": 1, "resultName": "AGREE", "txExecutionResult": 1}, True),
            ("vercel-item2-rewrite-recovery-current.json", {"status": 6, "result": 5, "resultName": "NO_MAJORITY", "txExecutionResult": 1}, False),
        ]
        for name, receipt, expected in examples:
            with self.subTest(receipt=name):
                self.assertEqual(chain_receipts.successful(receipt), expected)
                self.assertEqual(chain_receipts.successful({**receipt, "status": 7}), expected)

    def test_runner_stops_on_finalized_no_majority(self):
        runner = run_case.Runner(self.args)
        receipt = {"status": 7, "result": 5, "txExecutionResult": 1}
        with patch.object(run_case, "fetch_receipt", return_value=receipt):
            with self.assertRaisesRegex(SystemExit, "ended FINALIZED"):
                runner.wait({"key": "probe:0:2:REWRITE", "tx": "0xabc"})
        self.assertNotIn("0xabc", runner.confirmed)

    def test_acknowledged_failure_preserves_hash_without_duplicate(self):
        runner = run_case.Runner(self.args)
        sent = subprocess.CompletedProcess([], 0, "Transaction Hash: 0xabc\n", "")
        failed = {"status": 6, "result": 5, "txExecutionResult": 1}
        key = "probe:0:2:REWRITE"
        call_args = ["0", "2", "REWRITE", "same-envelope"]
        with patch.object(run_case.subprocess, "run", return_value=sent) as write:
            with patch.object(run_case, "fetch_receipt", return_value=failed):
                with self.assertRaisesRegex(SystemExit, "UNDETERMINED"):
                    runner.send(key, "probe", call_args)
                self.args.acknowledge_failed = ["0xabc"]
                resumed = run_case.Runner(self.args)
                resumed.resume()
                self.assertFalse(resumed.send(key, "probe", call_args))
            self.assertEqual(write.call_count, 1)
        self.assertEqual(run_case.manifest_rows(self.args.manifest)[key]["tx"], "0xabc")
        self.assertIn("0xabc", resumed.acknowledged)
        self.assertNotIn("0xabc", resumed.confirmed)

    def test_pending_acknowledgement_still_waits_for_consensus(self):
        self.args.acknowledge_failed = ["0xabc"]
        runner = run_case.Runner(self.args)
        with patch.object(run_case, "fetch_receipt", side_effect=[
            {"status": 1}, {"status": 5, "result": 1, "txExecutionResult": 1},
        ]) as fetch:
            runner.wait({"key": "probe:0:2:REWRITE", "tx": "0xabc"})
            self.assertEqual(fetch.call_count, 2)
        self.assertNotIn("0xabc", runner.acknowledged)
        self.assertIn("0xabc", runner.confirmed)

    def test_finalized_leader_timeout_resumes_only_with_ack_without_duplicate(self):
        runner = run_case.Runner(self.args)
        sent = subprocess.CompletedProcess([], 0, "Transaction Hash: 0xabc\n", "")
        key, call_args = "probe:0:2:REWRITE", ["0", "2", "REWRITE", "same-envelope"]
        with patch.object(run_case.subprocess, "run", return_value=sent) as write:
            with patch.object(run_case, "fetch_receipt", return_value={
                "status": 13, "result": 0, "txExecutionResult": 0,
            }):
                with self.assertRaisesRegex(SystemExit, "LEADER_TIMEOUT"):
                    runner.send(key, "probe", call_args)
            finalized = {"status": 7, "statusName": "FINALIZED", "result": 0, "resultName": "IDLE",
                         "txExecutionResult": 0, "txExecutionResultName": "NOT_VOTED"}
            with patch.object(run_case, "fetch_receipt", return_value=finalized):
                with self.assertRaisesRegex(SystemExit, "FINALIZED / NOT_VOTED / IDLE"):
                    run_case.Runner(self.args).resume()
                self.args.acknowledge_failed = ["0xabc"]
                resumed = run_case.Runner(self.args)
                resumed.resume()
                self.assertFalse(resumed.send(key, "probe", call_args))
            self.assertEqual(write.call_count, 1)
        self.assertIn("0xabc", resumed.acknowledged)
        self.assertNotIn("0xabc", resumed.confirmed)
        self.assertEqual(run_case.manifest_rows(self.args.manifest)[key]["tx"], "0xabc")

    def test_finalized_negative_result_can_be_acknowledged_without_becoming_success(self):
        self.args.acknowledge_failed = ["0xabc"]
        for result in ("NO_MAJORITY", "TIMEOUT", "DETERMINISTIC_VIOLATION",
                       "DISAGREE", "MAJORITY_DISAGREE"):
            with self.subTest(result=result):
                runner = run_case.Runner(self.args)
                receipt = {"status": 7, "resultName": result, "txExecutionResult": 1}
                with patch.object(run_case, "fetch_receipt", return_value=receipt):
                    runner.wait({"key": "probe:0:2:REWRITE", "tx": "0xabc"})
                self.assertIn("0xabc", runner.acknowledged)
                self.assertNotIn("0xabc", runner.confirmed)

    def test_finalized_known_unsuccessful_execution_can_be_acknowledged(self):
        self.args.acknowledge_failed = ["0xabc"]
        for result, execution in ((0, 0), (1, 2), (3, 3), (2, 4)):
            with self.subTest(result=result, execution=execution):
                runner = run_case.Runner(self.args)
                receipt = {"status": 7, "result": result, "txExecutionResult": execution}
                self.assertTrue(chain_receipts.finalized_failure(receipt))
                self.assertFalse(chain_receipts.successful(receipt))
                with patch.object(run_case, "fetch_receipt", return_value=receipt):
                    runner.wait({"key": "probe:0:2:REWRITE", "tx": "0xabc"})
                self.assertIn("0xabc", runner.acknowledged)
                self.assertNotIn("0xabc", runner.confirmed)

    def test_finalized_ambiguous_outcome_cannot_be_acknowledged(self):
        self.args.acknowledge_failed = ["0xabc"]
        examples = [
            {"status": 7, "txExecutionResult": 1},
            {"status": 7, "txExecutionResult": 1, "result": "future_result"},
            {"status": 7, "txExecutionResult": 1, "result": 0},
            {"status": 7, "txExecutionResult": 1, "result": 5, "resultName": "AGREE"},
            {"status": 7, "txExecutionResult": 0},
            {"status": 7, "result": 5},
            {"status": 7, "txExecutionResult": "future_execution", "result": 0},
            {"status": 7, "txExecutionResult": 0, "txExecutionResultName": "FINISHED_WITH_RETURN", "result": 0},
            {"status": 7, "txExecutionResult": 1, "result": 6},
            {"status": 7, "txExecutionResult": 1, "result": 6, "resultName": "MAJORITY_AGREE"},
            {"status": 7, "txExecutionResult": 1, "result": 7},
            {"status": 7, "txExecutionResult": 1, "result": 7, "resultName": "MAJORITY_DISAGREE"},
            {"status": 7, "txExecutionResult": 5, "result": 4},
            {"status": 7, "txExecutionResult": 5, "txExecutionResultName": "DETERMINISTIC_VIOLATION", "result": 4},
        ]
        for receipt in examples:
            with self.subTest(receipt=receipt):
                runner = run_case.Runner(self.args)
                self.assertFalse(chain_receipts.finalized_failure(receipt))
                self.assertFalse(chain_receipts.successful(receipt))
                with patch.object(run_case, "fetch_receipt", return_value=receipt):
                    with self.assertRaisesRegex(SystemExit, "ended FINALIZED"):
                        runner.wait({"key": "probe:0:2:REWRITE", "tx": "0xabc"})
                self.assertNotIn("0xabc", runner.acknowledged)
                self.assertNotIn("0xabc", runner.confirmed)

    def test_conflicting_status_and_execution_aliases_fail_closed(self):
        for receipt in (
            {"status": 6, "statusName": "FINALIZED", "result": 0, "txExecutionResult": 0},
            {"status": 7, "result": 0, "txExecutionResult": 0, "txExecutionResultName": "FINISHED_WITH_RETURN"},
            {"status": 7, "result": 1, "txExecutionResult": 1, "txExecutionResultName": "NOT_VOTED"},
        ):
            with self.subTest(receipt=receipt):
                self.assertFalse(chain_receipts.successful(receipt))
                self.assertFalse(chain_receipts.finalized_failure(receipt))
                self.assertFalse(chain_receipts.finalized_no_execution(receipt))

    def test_legacy_bradbury_status_codes_and_name_aliases(self):
        for code, name in ((9, "APPEAL_REVEALING"), (10, "APPEAL_COMMITTING"),
                           (11, "READY_TO_FINALIZE"), (12, "VALIDATORS_TIMEOUT"),
                           (13, "LEADER_TIMEOUT")):
            for value in (code, str(code), name, name.replace("_", ""),
                          "".join(word.title() for word in name.split("_"))):
                with self.subTest(code=code, value=value):
                    self.assertEqual(chain_receipts.status_of({"status": value}), name)
        self.assertEqual(chain_receipts.status_of({"status": 13, "statusName": "LeaderTimeout"}),
                         "LEADER_TIMEOUT")
        ready = {"status": 11, "txExecutionResult": 1}
        self.assertNotIn(chain_receipts.status_of(ready), chain_receipts.TERMINAL)
        self.assertFalse(chain_receipts.successful(ready))

    def test_leader_timeout_stops_before_polling_again(self):
        runner = run_case.Runner(self.args)
        receipt = {"status": 13, "statusName": "LEADER_TIMEOUT", "txExecutionResult": 0,
                   "lastRound": {"rotationsLeft": "3"}}
        with patch.object(run_case, "fetch_receipt", return_value=receipt) as fetch:
            with self.assertRaisesRegex(SystemExit, "ended LEADER_TIMEOUT / NOT_VOTED"):
                runner.wait({"key": "probe:0:0:PINNED", "tx": "0xabc"})
            self.assertEqual(fetch.call_count, 1)

    def test_appealed_timeout_resumes_same_hash_without_duplicate(self):
        runner = run_case.Runner(self.args)
        sent = subprocess.CompletedProcess([], 0, "Transaction Hash: 0xabc\n", "")
        with patch.object(run_case.subprocess, "run", return_value=sent) as write:
            with patch.object(run_case, "fetch_receipt", return_value={"status": 13, "txExecutionResult": 0}):
                with self.assertRaisesRegex(SystemExit, "LEADER_TIMEOUT"):
                    runner.send("probe:0:0:PINNED", "probe", ["0", "0", "PINNED", ""])
            self.assertEqual(run_case.manifest_rows(self.args.manifest)["probe:0:0:PINNED"]["tx"], "0xabc")
            resumed = run_case.Runner(self.args)
            with patch.object(run_case, "fetch_receipt", side_effect=[
                {"status": 2, "txExecutionResult": 0},
                {"status": 5, "txExecutionResult": 1},
            ]) as fetch:
                resumed.resume()
                self.assertFalse(resumed.send("probe:0:0:PINNED", "probe", ["0", "0", "PINNED", ""]))
                self.assertEqual([call.args[0] for call in fetch.call_args_list], ["0xabc", "0xabc"])
            self.assertEqual(write.call_count, 1)


if __name__ == "__main__":
    unittest.main()
