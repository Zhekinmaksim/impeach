"""Machine-readable contract reads preserve text and integer types."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))
import impeach


class ChainReadTests(unittest.TestCase):
    def test_json_read_preserves_long_multiline_text_and_exact_numbers(self):
        reply = "A line with 'quotes', + signs, and \\ escapes.\n" * 100
        expected = {"item_index": 1, "opened_at": 1791567831, "bond": 100000000000000001,
                    "rewrite_reply": reply, "literal": "123", "touched": True}
        result = subprocess.CompletedProcess([], 0, json.dumps(expected), "")
        with patch.object(impeach.subprocess, "run", return_value=result) as run:
            self.assertEqual(impeach.chain_call("0xcontract", "get_probe", [0, 1], "https://rpc", 17), expected)
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["node", str(ROOT / "scripts/genlayer_write.mjs"),
                                      "--read", "0xcontract", "get_probe"])
        self.assertEqual(json.loads(command[command.index("--args-json") + 1]), [0, 1])
        self.assertEqual(command[-2:], ["--rpc", "https://rpc"])
        self.assertEqual(run.call_args.kwargs["timeout"], 17)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_address_arguments_and_scalar_returns_keep_their_types(self):
        address = "0x" + "a" * 40
        for response in (0, 123456789012345678901234567890, False, None, "123"):
            with self.subTest(response=response):
                result = subprocess.CompletedProcess([], 0, json.dumps(response), "")
                with patch.object(impeach.subprocess, "run", return_value=result) as run:
                    actual = impeach.chain_call("0xcontract", "balance_of", [address])
                self.assertEqual(actual, response)
                self.assertIs(type(actual), type(response))
                command = run.call_args.args[0]
                self.assertEqual(json.loads(command[command.index("--args-json") + 1]), [address])

    def test_rpc_failures_timeouts_and_human_output_are_not_misparsed(self):
        result = subprocess.CompletedProcess([], 2, "", "RPC unavailable")
        with patch.object(impeach.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "RPC unavailable"):
                impeach.chain_call("0xcontract", "counts", [])
        with patch.object(impeach.subprocess, "run", side_effect=subprocess.TimeoutExpired("node", 7)):
            with self.assertRaises(subprocess.TimeoutExpired):
                impeach.chain_call("0xcontract", "counts", [], timeout=7)
        result = subprocess.CompletedProcess([], 0, "Result:\n{ reply: 'first' + 'second' }", "")
        with patch.object(impeach.subprocess, "run", return_value=result):
            with self.assertRaises(json.JSONDecodeError):
                impeach.chain_call("0xcontract", "counts", [])

    @unittest.skipUnless(shutil.which("node"), "node is required for the SDK bridge")
    def test_bridge_read_uses_no_keychain_and_serializes_raw_sdk_maps_and_bigints(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            package = base / "genlayer"
            sdk = package / "node_modules/genlayer-js"
            (sdk / "dist/chains").mkdir(parents=True)
            (sdk / "package.json").write_text('{"type":"module"}')
            (sdk / "dist/chains/index.js").write_text('export const testnetBradbury = {id: 4221};')
            text = "literal 123 0xabc + __BIGINT__\n'quoted'\\tail" * 20
            (sdk / "dist/index.js").write_text("""
export function createClient(options) {
  if (options.account) throw new Error('read unexpectedly received an account');
  return {async readContract(call) {
    if (call.jsonSafeReturn !== false) throw new Error('lossy JSON normalization');
    return new Map([['args', call.args], ['small', 2n], ['large', 100000000000000001n],
      ['nested', [false, null, new Map([['negative', -100000000000000001n]])]],
      ['text', TEXT], ['bytes', new Uint8Array([0, 255])]]);
  }};
}
export function createAccount() {throw new Error('read unexpectedly created a signer');}
""".replace("TEXT", json.dumps(text)))
            (package / "dist").mkdir()
            entry = package / "dist/cli.js"
            entry.write_text("#!/bin/sh\nexit 99\n")
            entry.chmod(0o755)
            binary = base / "bin"
            binary.mkdir()
            (binary / "genlayer").symlink_to(entry)
            marker = base / "keychain-touched"
            keytar = package / "node_modules/keytar/lib"
            keytar.mkdir(parents=True)
            (keytar / "keytar.js").write_text("require('node:fs').writeFileSync(" +
                                             json.dumps(str(marker)) + ", 'touched');\nmodule.exports = {};")
            config = base / "config.json"
            config.write_text('{"activeAccount":"must-not-read"}')
            args = [0, 1, "0x" + "a" * 40, "123"]
            result = subprocess.run([
                shutil.which("node"), str(ROOT / "scripts/genlayer_write.mjs"),
                "--read", "0x" + "b" * 40, "get_probe", "--args-json", json.dumps(args),
            ], capture_output=True, text=True, timeout=10,
                env={"PATH": str(binary) + os.pathsep + os.defpath, "HOME": str(base),
                     "GENLAYER_CONFIG": str(config)})
            self.assertEqual(result.returncode, 0, result.stderr)
            decoded = json.loads(result.stdout)
            self.assertEqual(decoded["args"], args)
            self.assertEqual(decoded["small"], 2)
            self.assertEqual(decoded["large"], 100000000000000001)
            self.assertEqual(decoded["nested"], [False, None, {"negative": -100000000000000001}])
            self.assertEqual(decoded["text"], text)
            self.assertEqual(decoded["bytes"], "0x00ff")
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
