"""Offline recovery checks; all RPC reads and transaction submissions are mocked."""

import contextlib
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import retry_finalized_probe as recovery
import run_case
from proof_fixture import make_bundle


class FinalizedProbeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.args = SimpleNamespace(
            address="0x" + "1" * 40, account="challenger", rpc="https://rpc.example",
            manifest=os.path.join(self.tmp.name, "case.jsonl"), tx="0x" + "a" * 64,
            claim=os.path.join(ROOT, "calibration", "claim-gsm8k.json"),
            dry_run=False, delay=0, wait_timeout=0.05, poll_interval=0.001,
        )
        self.new_tx = "0x" + "b" * 64
        self.claim = run_case.load_claim(self.args.claim)
        self.rewrites = run_case.load_rewrites(self.claim)
        self.challenge = {"status": "TRIAL", "claim_id": 0, "subset": [2], "trial_started_at": 100}
        self.clock = 120
        self.state = {"touched": True, "pinned": "RIGHT", "recall": "MISS", "rewrite_class": ""}
        self.receipt = {"status": 7, "result": 5, "txExecutionResult": 1, "rounds": [{"votes": [4, 3]}]}
        self.row = self.make_row()
        self.write_rows(self.row)
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.original_fetch = self.enterContext(patch.object(recovery, "fetch_receipt", return_value=self.receipt))
        self.new_fetch = self.enterContext(patch.object(run_case, "fetch_receipt", return_value={
            "status": 5, "result": 1, "txExecutionResult": 1,
        }))
        self.enterContext(patch.object(run_case.Runner, "read", side_effect=self.read))
        self.send = self.enterContext(patch.object(run_case.subprocess, "run", return_value=
            subprocess.CompletedProcess([], 0, "Transaction Hash: " + self.new_tx + "\n", "")))

    def make_row(self, mode="REWRITE", value=0):
        payload = run_case.tool.canonical_envelope(self.rewrites[2]) if mode == "REWRITE" else ""
        call_args = ["0", "2", mode, payload]
        signature = hashlib.sha256(json.dumps(["probe", call_args, str(value)],
                                             ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return {"key": "probe:0:2:" + mode, "tx": self.args.tx, "method": "probe", "at": 1,
                "address": self.args.address, "signature": signature, "step": "probe",
                "challenge_id": 0, "item_index": 2, "mode": mode}

    def write_rows(self, *rows):
        with open(self.args.manifest, "w", encoding="utf-8") as target:
            for row in rows:
                target.write(json.dumps(row) + "\n")

    def read_rows(self):
        with open(self.args.manifest, encoding="utf-8") as source:
            return [json.loads(line) for line in source]

    def read(self, method, *args):
        return {"get_challenge": self.challenge, "get_claim": {"trial_window_s": 30},
                "clock": self.clock, "get_probe": self.state}[method]

    def refuse(self, message):
        original = self.read_rows()
        with self.assertRaisesRegex(SystemExit, message):
            recovery.retry(self.args)
        self.send.assert_not_called()
        self.assertEqual(self.read_rows(), original)

    def test_appends_once_and_saves_complete_receipt_before_submission(self):
        def submit(command, **kwargs):
            self.assertEqual(self.read_rows(), [self.row])
            folder = self.args.manifest + ".receipts"
            names = [name for name in os.listdir(folder) if ".finalized-" in name]
            self.assertEqual(len(names), 1)
            self.assertTrue(os.path.isfile(recovery.dispatch_path(self.args.manifest, self.args.tx)))
            with open(os.path.join(folder, names[0]), encoding="utf-8") as source:
                self.assertEqual(json.load(source), self.receipt)
            self.assertEqual(command[command.index("--value") + 1], "0")
            self.assertEqual(json.loads(command[command.index("--args-json") + 1]),
                             recovery.original_call(self.row, self.args.claim))
            return subprocess.CompletedProcess([], 0, "Transaction Hash: " + self.new_tx + "\n", "")

        self.send.side_effect = submit
        recovery.retry(self.args)
        first, second = self.read_rows()
        self.assertEqual(first, self.row)
        self.assertEqual(second["previous_row"], self.row)
        self.assertEqual(second["previous_tx"], self.row["tx"])
        self.assertEqual(second["tx"], self.new_tx)
        self.assertEqual(second["signature"], first["signature"])
        self.assertFalse(os.path.isabs(second["previous_receipt"]))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, second["previous_receipt"])))
        with self.assertRaisesRegex(SystemExit, "latest manifest"):
            recovery.retry(self.args)
        self.args.tx = self.new_tx
        with self.assertRaisesRegex(SystemExit, "already has a recovery"):
            recovery.retry(self.args)
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(len(self.read_rows()), 2)

    def test_subject_deadline_rereads_chain_clock_after_evidence_before_marker(self):
        self.args.subject_deadline = 245
        original_save = recovery.save_receipt
        def save(*args, **kwargs):
            path = original_save(*args, **kwargs)
            # The court remains open until 130; the subject cutoff is 125.
            self.clock = 125
            return path
        with patch.object(recovery.time, 'time', return_value=100), \
                patch.object(recovery, 'save_receipt', side_effect=save):
            self.refuse('subject deadline')
        self.assertFalse(os.path.exists(recovery.dispatch_path(self.args.manifest, self.args.tx)))
        self.assertEqual(len(list(Path(self.args.manifest + '.receipts').glob('*.json'))), 1)

    def test_subject_deadline_cli_is_optional_positive_integer_epoch(self):
        options = [value for name in ('address', 'account', 'rpc', 'manifest', 'tx')
                   for value in ('--' + name, getattr(self.args, name))]
        self.assertIsNone(recovery.parse_args(options).subject_deadline)
        self.assertEqual(recovery.parse_args(options + ['--subject-deadline', '1791720000']).subject_deadline,
                         1791720000)
        for value in ('0', '-1', '1.5'):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                recovery.parse_args(options + ['--subject-deadline', value])

    def write_subject_policy(self, deadline, **changes):
        fingerprint = hashlib.sha256(json.dumps([self.claim, self.rewrites], sort_keys=True,
                                                ensure_ascii=False).encode()).hexdigest()
        identity = {'address': self.args.address.lower(), 'challenge_id': 0,
                    'input_sha256': fingerprint, 'subject_first': True, 'subject_deadline': deadline}
        identity.update(changes)
        path = Path(self.args.manifest + '.complete/identity.json')
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(identity))

    def test_standalone_retry_inherits_expired_subject_policy_without_cli_flag(self):
        self.write_subject_policy(1)
        with patch.object(recovery.time, 'time', return_value=100):
            self.refuse('subject deadline')
        self.assertFalse(os.path.exists(recovery.dispatch_path(self.args.manifest, self.args.tx)))

    def test_standalone_retry_inherits_valid_subject_policy_without_mutating_args(self):
        self.write_subject_policy(245)
        with patch.object(recovery.time, 'time', return_value=100):
            self.assertEqual(recovery.retry(self.args), 0)
        self.assertEqual(self.send.call_count, 1)
        self.assertFalse(hasattr(self.args, 'subject_deadline'))
        self.assertEqual(self.read_rows()[1]['previous_row'], self.row)

    def test_standalone_retry_rejects_changed_subject_deadline_or_identity(self):
        self.write_subject_policy(245)
        for deadline in (244, 246):
            with self.subTest(deadline=deadline):
                self.args.subject_deadline = deadline
                self.refuse('subject deadline differs')
        self.args.subject_deadline = None
        for changes in ({'address': '0x' + '2' * 40}, {'challenge_id': 1},
                        {'input_sha256': '0' * 64}, {'subject_first': False}):
            with self.subTest(changes=changes):
                self.write_subject_policy(245, **changes)
                self.refuse('subject.*(policy|identity)|frozen subject')
        self.assertFalse(os.path.exists(recovery.dispatch_path(self.args.manifest, self.args.tx)))

    def setup_no_messages_proof(self, during_lookup=None):
        self.args.allow_proven_no_messages=True
        self.args.source=os.path.join(ROOT,'build/impeach.py')
        self.receipt={'status':7,'result':0,'txExecutionResult':1}
        self.original_fetch.return_value=self.receipt
        self.challenge.update(challenge_id=0)
        self.state.update(challenge_id=0,item_index=2,rewrite='',stage_c1='PENDING',stage_c2='PENDING')
        chain=copy.deepcopy(self.claim);chain.update(self.claim['extras'])
        chain.update(claim_id=0,status='TRIAL',active_challenge=0,
            item_hashes=[run_case.tool.item_commitment(i['prompt'],i['answer'],i['salt']) for i in self.claim['_items']],
            stake=int(self.claim['stake']),bond_sworn=int(self.claim['bond']))
        def read(method,*args):
            return copy.deepcopy({'get_claim':chain,'get_challenge':self.challenge,'get_probe':self.state,'clock':self.clock}[method])
        self.enterContext(patch.object(run_case.Runner,'read',side_effect=read))
        self.proof_writes=[]
        def command(command,**kwargs):
            if command[1]=='scripts/native_finality_proof.mjs':
                bundle=make_bundle(self.row,recovery.original_call(self.row,self.args.claim),
                    source_sha=hashlib.sha256(Path(self.args.source).read_bytes()).hexdigest(),
                    claim_sha=recovery.proof.claim_hash(self.args.claim))
                if during_lookup:during_lookup()
                return subprocess.CompletedProcess(command,0,json.dumps(bundle),'')
            self.proof_writes.append(command)
            return subprocess.CompletedProcess(command,0,'Transaction Hash: '+self.new_tx+'\n','')
        self.send.side_effect=command
        return chain

    def test_proof_rechecks_empty_slot_and_deadline_after_lookup_before_marker(self):
        self.setup_no_messages_proof(lambda:self.state.update(stage_c1='INADMISSIBLE'))
        with self.assertRaisesRegex(SystemExit,'state changed'):recovery.retry(self.args)
        self.assertEqual(self.proof_writes,[])
        self.assertFalse(Path(recovery.dispatch_path(self.args.manifest,self.args.tx)).exists())
        self.state['stage_c1']='PENDING'
        chain=self.setup_no_messages_proof(lambda:setattr(self,'clock',100+self.claim['extras']['trial_window_s']))
        with self.assertRaisesRegex(SystemExit,'window closed'):recovery.retry(self.args)
        self.assertEqual(self.proof_writes,[])
        self.assertFalse(Path(recovery.dispatch_path(self.args.manifest,self.args.tx)).exists())

    def test_proof_frozen_claim_or_slot_identity_mismatch_refuses_before_lookup(self):
        chain=self.setup_no_messages_proof()
        chain['score_milli']+=1
        with self.assertRaisesRegex(ValueError,'frozen claim'):recovery.retry(self.args)
        self.send.assert_not_called()
        chain['score_milli']-=1;self.state['item_index']=3
        with self.assertRaisesRegex(ValueError,'identity differs'):recovery.retry(self.args)
        self.send.assert_not_called()

    def test_pending_unfinalized_success_and_unknown_results_refuse(self):
        for receipt in (
            {"status": 1, "result": 5}, {"status": 6, "result": 5},
            {"status": 11, "result": 5}, {"status": 7, "result": 1},
            {"status": 7}, {"status": 7, "result": "future_result"},
            {"status": 7, "result": 5, "resultName": "AGREE"},
            {"status": 7, "result": 5},
            {"status": 7, "result": 1, "txExecutionResult": 2},
            {"status": 7, "result": 0, "txExecutionResult": 1},
            {"status": 7, "result": 0, "txExecutionResult": 0, "txExecutionResultName": "FINISHED_WITH_RETURN"},
        ):
            with self.subTest(receipt=receipt):
                self.original_fetch.return_value = receipt
                self.refuse("FINALIZED with an explicit negative")

    def test_finalized_idle_not_voted_can_retry_untouched_slot_once(self):
        self.original_fetch.return_value = {
            "status": 7, "statusName": "FINALIZED", "result": 0, "resultName": "IDLE",
            "txExecutionResult": 0, "txExecutionResultName": "NOT_VOTED",
        }
        recovery.retry(self.args)
        old, new = self.read_rows()
        self.assertEqual(old, self.row)
        self.assertEqual(new["previous_tx"], old["tx"])
        self.assertEqual(self.send.call_count, 1)
        with open(os.path.join(self.tmp.name, new["previous_receipt"]), encoding="utf-8") as source:
            self.assertEqual(json.load(source), self.original_fetch.return_value)
        self.args.tx = self.new_tx
        with self.assertRaisesRegex(SystemExit, "already has a recovery"):
            recovery.retry(self.args)
        self.assertEqual(self.send.call_count, 1)

    def test_finalized_no_execution_does_not_bypass_closed_trial(self):
        self.original_fetch.return_value = {"status": 7, "result": 0, "txExecutionResult": 0}
        self.challenge["status"] = "RULED"
        self.refuse("active TRIAL")
        self.challenge["status"] = "TRIAL"
        self.clock = 131
        self.refuse("window has closed")
        self.assertFalse(os.path.exists(recovery.dispatch_path(self.args.manifest, self.args.tx)))

    def test_nonzero_values_and_other_methods_or_steps_refuse(self):
        for row in ({**self.row, "value": 1}, self.make_row(value=1),
                    {**self.row, "method": "open_claim"}, {**self.row, "step": "retry"}):
            with self.subTest(row=row):
                self.write_rows(row)
                self.refuse("zero-value|nonzero|original probe")

    def test_current_rewrite_must_match_original_signature(self):
        rewrites = copy.deepcopy(self.rewrites)
        rewrites[2]["prompt"] += " Changed wording."
        with patch.object(run_case, "load_rewrites", return_value=rewrites):
            self.refuse("signature does not match")

    def test_each_applied_slot_refuses(self):
        occupied = {
            "PINNED": {"touched": True, "pinned": "DEAD"},
            "RECALL": {"touched": True, "recall": "MISS"},
            "REWRITE": {"touched": True, "rewrite_class": "paraphrase"},
            "ADMIT": {"touched": True, "stage_c1": "ADMISSIBLE", "stage_c2": "INADMISSIBLE"},
        }
        for mode, state in occupied.items():
            with self.subTest(mode=mode):
                self.write_rows(self.make_row(mode))
                self.state = state
                self.refuse("already applied or not ready")

    def test_empty_slots_and_pending_second_framing_are_eligible(self):
        for mode in ("PINNED", "RECALL", "REWRITE", "ADMIT"):
            with self.subTest(mode=mode):
                self.args.tx = "0x" + str(("PINNED", "RECALL", "REWRITE", "ADMIT").index(mode) + 1) * 64
                self.write_rows(self.make_row(mode))
                self.state = ({"touched": True, "stage_c1": "ADMISSIBLE", "stage_c2": "PENDING"}
                              if mode == "ADMIT" else {"touched": False})
                recovery.retry(self.args)
                self.assertEqual(len(self.read_rows()), 2)

    def test_closed_trial_and_expired_window_refuse(self):
        self.challenge["status"] = "RULED"
        self.refuse("active TRIAL")
        self.challenge["status"] = "TRIAL"
        self.clock = 131
        self.refuse("window has closed")

    def test_missing_slot_fields_do_not_imply_untouched(self):
        self.state = {"touched": True}
        self.refuse("already applied or not ready")
        self.state = {}
        self.refuse("already applied or not ready")

    def test_original_hash_must_still_be_latest_for_its_key(self):
        self.write_rows(self.row, {**self.row, "tx": self.new_tx})
        self.refuse("latest manifest")

    def test_does_not_resume_an_unrelated_pending_transaction(self):
        other = {"key": "open", "tx": "0x" + "c" * 64, "method": "open_claim",
                 "step": "open", "address": self.args.address}
        self.write_rows(other, self.row)
        recovery.retry(self.args)
        self.assertEqual(self.read_rows()[0], other)
        self.assertEqual(self.original_fetch.call_args.args[0], self.args.tx)
        self.assertEqual(self.new_fetch.call_args.args[0], self.new_tx)
        self.assertEqual(self.original_fetch.call_count, 1)
        self.assertEqual(self.new_fetch.call_count, 1)

    def test_dry_run_checks_and_preserves_history_without_submission(self):
        self.args.dry_run = True
        recovery.retry(self.args)
        self.send.assert_not_called()
        self.assertEqual(self.read_rows(), [self.row])
        self.original_fetch.assert_called_once()
        self.assertFalse(os.path.exists(recovery.dispatch_path(self.args.manifest, self.args.tx)))

    def test_crash_with_unknown_submission_outcome_blocks_second_dispatch(self):
        self.send.side_effect = RuntimeError("connection lost before the new hash was recorded")
        with self.assertRaisesRegex(RuntimeError, "connection lost"):
            recovery.retry(self.args)
        self.assertEqual(self.read_rows(), [self.row])
        marker = recovery.dispatch_path(self.args.manifest, self.args.tx)
        with open(marker, encoding="utf-8") as source:
            self.assertEqual(json.load(source)["previous_tx"], self.args.tx)
        with self.assertRaisesRegex(SystemExit, "reconcile its on-chain outcome"):
            recovery.retry(self.args)
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.original_fetch.call_count, 1)
        self.assertTrue(os.path.isfile(marker))

    def test_concurrent_recovery_cannot_submit_a_second_attempt(self):
        with open(self.args.manifest + ".retry.lock", "a", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.refuse("another recovery")

    def test_three_recoveries_preserve_inputs_ordinals_and_prebroadcast_evidence(self):
        self.args.max_recoveries = 3
        original_bytes = Path(self.args.manifest).read_bytes()
        receipts = [self.receipt, {"status": 7, "result": 0, "txExecutionResult": 0},
                    {"status": 7, "result": 2, "txExecutionResult": 1}]
        saved = {}
        for ordinal, receipt in enumerate(receipts, 1):
            previous = self.read_rows()[-1]
            self.args.tx = previous["tx"]
            self.original_fetch.return_value = receipt
            tx = "0x" + format(ordinal, "064x")

            def submit(command, **kwargs):
                marker = json.loads(Path(recovery.dispatch_path(self.args.manifest, previous["tx"])).read_text())
                self.assertEqual(marker["recovery_ordinal"], ordinal)
                self.assertEqual(marker["previous_row"], previous)
                path = Path(self.tmp.name) / marker["previous_receipt"]
                raw = path.read_bytes()
                self.assertEqual(json.loads(raw), receipt)
                self.assertEqual(marker["previous_receipt_sha256"], hashlib.sha256(raw).hexdigest())
                saved[path] = raw
                self.assertEqual(json.loads(command[command.index("--args-json") + 1]),
                                 recovery.original_call(self.row, self.args.claim))
                return subprocess.CompletedProcess([], 0, "Transaction Hash: " + tx + "\n", "")

            self.send.side_effect = submit
            recovery.retry(self.args)
            latest = self.read_rows()[-1]
            self.assertEqual(latest["previous_row"], previous)
            self.assertEqual(latest["recovery_ordinal"], ordinal)
            self.assertEqual(recovery.validate_history(latest, self.args.manifest), ordinal)
            self.assertTrue(Path(self.args.manifest).read_bytes().startswith(original_bytes))
            original_bytes = Path(self.args.manifest).read_bytes()
        self.args.tx = tx
        with self.assertRaisesRegex(SystemExit, "configured limit"):
            recovery.retry(self.args)
        self.assertEqual(self.send.call_count, 3)
        self.assertEqual(len(self.read_rows()), 4)
        for path, raw in saved.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_larger_limit_does_not_retry_pending_replay_or_finalized_return_idle(self):
        recovery.retry(self.args)
        self.args.tx = self.new_tx
        self.args.max_recoveries = 3
        self.send.reset_mock()
        for status, result, execution in ((1, 0, 0), (4, 0, 0), (14, 1, 1),
                                          (6, 5, 1), (11, 5, 1), (12, 3, 3), (7, 0, 1)):
            with self.subTest(status=status, result=result, execution=execution):
                self.original_fetch.return_value = {"status": status, "result": result, "txExecutionResult": execution}
                self.refuse("FINALIZED with an explicit negative")
        self.assertFalse(os.path.exists(recovery.dispatch_path(self.args.manifest, self.new_tx)))

    def test_recovery_history_cannot_be_reset_or_tampered_with(self):
        recovery.retry(self.args)
        first, second = self.read_rows()
        self.args.tx, self.args.max_recoveries = self.new_tx, 3
        self.send.reset_mock()
        for change in (lambda r: r.update(recovery_ordinal=0),
                       lambda r: r.update(previous_tx="0x"+"c"*64),
                       lambda r: r["previous_row"].update(signature="changed"),
                       lambda r: r["previous_row"].update(at=999),
                       lambda r: r.pop("previous_row"),
                       lambda r: [r.pop(k, None) for k in list(r) if k.startswith("previous_") or k == "recovery_ordinal"]):
            corrupted = copy.deepcopy(second)
            change(corrupted)
            self.write_rows(first, corrupted)
            self.refuse("invalid recovery history")
        self.write_rows(first, second)
        path = Path(self.tmp.name) / second["previous_receipt"]
        raw = path.read_bytes()
        path.write_bytes(raw + b" ")
        self.refuse("receipt evidence changed")
        path.unlink()
        self.refuse("receipt evidence is missing")

    def test_legacy_one_recovery_history_can_opt_in_without_rewriting_old_rows(self):
        recovery.retry(self.args)
        first, second = self.read_rows()
        second.pop("recovery_ordinal")
        second.pop("previous_receipt_sha256")
        self.write_rows(first, second)
        before = Path(self.args.manifest).read_bytes()
        self.args.tx, self.args.max_recoveries = self.new_tx, 3
        self.send.return_value = subprocess.CompletedProcess([], 0, "Transaction Hash: 0x"+"c"*64+"\n", "")
        recovery.retry(self.args)
        self.assertEqual(self.read_rows()[-1]["recovery_ordinal"], 2)
        self.assertEqual(self.read_rows()[-1]["previous_row"], second)
        self.assertTrue(Path(self.args.manifest).read_bytes().startswith(before))

    def test_inputs_and_applied_rewrite_outcomes_still_block_later_recoveries(self):
        recovery.retry(self.args)
        self.args.tx, self.args.max_recoveries = self.new_tx, 3
        self.send.reset_mock()
        rewrites = copy.deepcopy(self.rewrites)
        rewrites[2]["prompt"] += " Changed wording."
        with patch.object(run_case, "load_rewrites", return_value=rewrites):
            self.refuse("signature does not match")
        for extra in ({"stage_c1": "INADMISSIBLE"}, {"rewrite": "DEAD"}):
            self.state.update(extra)
            self.refuse("already applied or not ready")

    def test_unknown_second_recovery_dispatch_remains_exclusive(self):
        recovery.retry(self.args)
        self.args.tx, self.args.max_recoveries = self.new_tx, 3
        self.send.side_effect = RuntimeError("lost second recovery hash")
        with self.assertRaisesRegex(RuntimeError, "lost second recovery"):
            recovery.retry(self.args)
        marker = json.loads(Path(recovery.dispatch_path(self.args.manifest, self.args.tx)).read_text())
        self.assertEqual(marker["recovery_ordinal"], 2)
        with self.assertRaisesRegex(SystemExit, "reconcile its on-chain outcome"):
            recovery.retry(self.args)
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(len(self.read_rows()), 2)

    def test_completion_lock_deadline_margin_and_maximum_are_enforced(self):
        with open(self.args.manifest + ".complete.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.refuse("another completion process")
        self.args.deadline_margin = 10
        self.refuse("window has closed")
        self.args.deadline_margin = 0
        for limit in (0, 4, True):
            self.args.max_recoveries = limit
            self.refuse("integer from 1 to 3")

    def test_cli_recovery_policy_defaults_to_one_and_is_bounded(self):
        options = [value for name in ("address", "account", "rpc", "manifest", "tx")
                   for value in ("--" + name, getattr(self.args, name))]
        self.assertEqual(recovery.parse_args(options).max_recoveries, 1)
        self.assertEqual(recovery.parse_args(options + ["--max-recoveries", "3"]).max_recoveries, 3)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            recovery.parse_args(options + ["--max-recoveries", "4"])


if __name__ == "__main__":
    unittest.main()
