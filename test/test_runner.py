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
        self.assertTrue(chain_receipts.successful({"status": 7, "txExecutionResult": 1}))


if __name__ == "__main__":
    unittest.main()
