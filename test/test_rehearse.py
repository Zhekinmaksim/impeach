"""The local rehearsal must send the same frozen requests as the live claim."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rehearse


class RehearsalTests(unittest.TestCase):
    def test_uses_claim_terms_and_decode_parameters(self):
        claim = rehearse.load_claim(os.path.join(ROOT, "calibration", "claim-gsm8k.json"))
        claim["decode_params"] = {"temperature": 0, "max_tokens": 2048, "seed": 123}
        claim["prompt_template"]["system"] = "A custom frozen system instruction."
        claim["delta_threshold"] = 300
        claim["recall_threshold"] = 200
        requests = []

        def http(url, body):
            requests.append(json.loads(body))
            return 200, json.dumps({"choices": [{"message": {"content": "ANSWER: 0"}}]}).encode()

        driver, cid, verdict, certificate = rehearse.run_rehearsal(claim, "test-model", 0, http)
        frozen = driver.view("get_claim", cid)
        self.assertEqual(len(requests), 72)
        scored = [r for r in requests if not r["messages"][-1]["content"].startswith(rehearse.pop.RECALL_INSTRUCTION)]
        self.assertEqual(len(scored), 48)
        self.assertTrue(all(r["max_tokens"] == 2048 for r in scored))
        self.assertTrue(all(r["seed"] == 123 for r in requests))
        self.assertTrue(all(r["model"] == "test-model" for r in requests))
        self.assertEqual(requests[0]["messages"][0]["content"], claim["prompt_template"]["system"])
        for key in ("delta_threshold", "recall_threshold", "min_items", "scoring_rule"):
            self.assertEqual(frozen[key], claim[key])
        self.assertEqual(frozen["trial_window_s"], claim["extras"]["trial_window_s"])
        self.assertEqual(frozen["bond_sworn"], int(claim["bond"]))
        self.assertEqual(certificate["admissible_probes"], 24)
        self.assertEqual(verdict, "CLEAN")


if __name__ == "__main__":
    unittest.main()
