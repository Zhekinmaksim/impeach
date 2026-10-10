"""Publication gates for the offline collector; no wallet or network is used."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect


class CollectorTests(unittest.TestCase):
    def test_recovery_keeps_both_failed_and_successful_transactions(self):
        txs = {}
        old = {"key": "probe:0:2:REWRITE", "tx": "0xold", "status": "FINALIZED",
               "execution": "FINISHED_WITH_RETURN", "consensus_result": "NO_MAJORITY"}
        new = dict(old, tx="0xnew", status="ACCEPTED", consensus_result="AGREE", previous_tx="0xold")
        collect.record_transaction(txs, old)
        collect.record_transaction(txs, new)
        collect.record_transaction(txs, new)
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[old["key"]]["consensus_result"], "NO_MAJORITY")
        self.assertEqual(txs[new["key"] + "@0xnew"]["previous_tx"], "0xold")

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.recorded = cls.directory / "reads.json"
        subprocess.run([
            sys.executable, "scripts/simulate.py", "--record", str(cls.recorded),
            "--out", str(cls.directory / "simulation.json"),
        ], cwd=ROOT, check=True, capture_output=True, text=True)

    def collect(self, source, target):
        return subprocess.run([
            sys.executable, "scripts/collect.py", "test/fixtures/manifest.jsonl",
            "--from-json", str(source), "--address", "0x" + "1" * 40,
            "--out", str(target),
        ], cwd=ROOT, capture_output=True, text=True)

    def test_recorded_scripted_reads_never_become_bradbury_evidence(self):
        target = self.directory / "offline-case.json"
        result = self.collect(self.recorded, target)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        snapshot = json.loads(target.read_text())
        self.assertEqual(snapshot["provenance"], "simulation")
        self.assertIn("not verified chain evidence", snapshot["note"])
        self.assertEqual(snapshot["receipts"]["by_status"]["UNDETERMINED"], 1)
        original = json.loads(self.recorded.read_text())
        self.assertEqual(snapshot["cases"][0]["certificate"],
                         original["reads"][json.dumps(["certificate", [0]])])
        recomputed = subprocess.run([
            sys.executable, "cli/impeach.py", "recompute", str(target),
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(recomputed.returncode, 0, recomputed.stdout + recomputed.stderr)

    def test_revealed_unruled_claim_does_not_replace_existing_snapshot(self):
        recorded = json.loads(self.recorded.read_text())
        cert = recorded["reads"][json.dumps(["certificate", [0]])]
        cert.update(contested=False, under_challenge=True, ruled_at=0,
                    challenge_id=-1, verdict="UNCONTESTED", reason="")
        claim = recorded["reads"][json.dumps(["get_claim", [0]])]
        self.assertGreater(claim["burned_at"], 0)
        source = self.directory / "unruled-reads.json"
        source.write_text(json.dumps(recorded))
        target = self.directory / "preserved-case.json"
        previous = '{"existing":"published evidence"}\n'
        target.write_text(previous)
        result = self.collect(source, target)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(target.read_text(), previous)
        self.assertIn("No ruled certificate", result.stdout)

    def test_probe_only_manifest_keeps_case_transaction_evidence(self):
        rows = [json.loads(line) for line in (ROOT / "test/fixtures/manifest.jsonl").read_text().splitlines()]
        probes = [row for row in rows if row["step"] == "probe"]
        manifest = self.directory / "probes-only.jsonl"
        manifest.write_text("".join(json.dumps(row) + "\n" for row in probes))
        target = self.directory / "probes-only-case.json"
        result = subprocess.run([
            sys.executable, "scripts/collect.py", str(manifest),
            "--from-json", str(self.recorded), "--out", str(target),
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        published = json.loads(target.read_text())
        self.assertEqual(published["receipts"]["total"], len(probes))
        self.assertEqual({entry["tx"] for entry in published["cases"][0]["txs"].values()},
                         {row["tx"] for row in probes})

    def test_live_collection_rejects_mismatched_manifest_before_network(self):
        source = self.directory / "wrong-contract.jsonl"
        source.write_text(json.dumps({"key": "open", "tx": "0xold", "address": "0x" + "2" * 40}) + "\n")
        target = self.directory / "wrong-contract-case.json"
        result = subprocess.run([
            sys.executable, "scripts/collect.py", str(source), "--address", "0x" + "1" * 40,
            "--rpc", "http://127.0.0.1:1", "--out", str(target),
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manifest belongs to a different", result.stderr)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
