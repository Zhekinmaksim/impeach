"""Offline checks for the reproducible deployment artifact and gas guard."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_contract


class DeploymentTests(unittest.TestCase):
    def test_compaction_preserves_executable_ast_and_published_artifact(self):
        source = (ROOT / "contracts" / "impeach.py").read_text()
        loader, compact, manifest = build_contract.build(source)
        # GenVM parses consecutive leading comment lines as one JSON runner
        # directive. Provenance belongs in the manifest, never that comment block.
        lines = loader.splitlines()
        runner_comment = ""
        for line in lines:
            if not line.startswith("#"):
                break
            runner_comment += line[1:]
        self.assertEqual(json.loads(runner_comment)["Depends"],
                         json.loads(source.splitlines()[0].removeprefix("# "))["Depends"])
        self.assertFalse(lines[1].lstrip().startswith("#"))
        expected = build_contract.WithoutDocstrings().visit(ast.parse(source))
        self.assertEqual(ast.dump(expected), ast.dump(ast.parse(compact)))
        self.assertEqual(manifest["source_sha256"], hashlib.sha256(source.encode()).hexdigest())
        # Soft source-size budget. The bridge separately simulates deployment
        # below Bradbury's 16,777,216 gas cap before signing (v2: 15.15M estimate).
        self.assertLess(manifest["artifact_bytes"], 19000)
        self.assertEqual(loader, (ROOT / "build" / "impeach.py").read_text())
        self.assertEqual(compact, (ROOT / "build" / "impeach.readable.py").read_text())

    def test_gas_guard(self):
        result = subprocess.run(["node", "--test", str(ROOT / "test" / "test_gas.mjs")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
