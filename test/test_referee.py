import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test"))
import population
from drivers import StubDriver


class RefereeTests(unittest.TestCase):
    def setUp(self):
        self.corpus = population.load_corpus()
        self.driver = StubDriver(population.World(self.corpus))

    def ruling(self, response, control_index=10):
        env = next(e for e in self.corpus["controls"] if e["item_index"] == control_index)
        item = self.corpus["items"][control_index]
        self.driver.gl.nondet.handler = lambda prompt: json.dumps(response)
        return self.driver.contract._referee(1, env["class"], item["prompt"], item["answer"], env["prompt"], env["answer"])

    def test_computed_wrong_answer_cannot_be_overridden_by_true_boolean(self):
        original = self.corpus["items"][10]["answer"]
        self.assertEqual(self.ruling({"original_result": original, "rewrite_result": "55200",
                                      "same_question": True}), "INADMISSIBLE")

    def test_missing_computed_results_fail_closed(self):
        self.assertEqual(self.ruling({"same_question": True}), "INADMISSIBLE")

    def test_unit_control_independent_result_overrides_anchored_yes(self):
        self.assertEqual(self.ruling({"original_result": "243", "rewrite_result": "198.45",
                                      "same_question": True}, control_index=17), "INADMISSIBLE")

    def test_wrong_original_result_also_fails_closed(self):
        self.assertEqual(self.ruling({"original_result": "0", "rewrite_result": "57600",
                                      "same_question": True}), "INADMISSIBLE")

    def test_blind_solver_cannot_see_the_supplied_answer_key(self):
        prompts = []
        env = next(e for e in self.corpus["controls"] if e["item_index"] == 10)
        item = self.corpus["items"][10]
        def model(prompt):
            prompts.append(prompt)
            return json.dumps({"original_result": item["answer"], "rewrite_result": "55200", "same_question": True})
        self.driver.gl.nondet.handler = model
        result = self.driver.contract._referee(1, env["class"], item["prompt"], item["answer"], env["prompt"], env["answer"])
        self.assertEqual(result, "INADMISSIBLE")
        self.assertEqual(len(prompts), 2)
        self.assertNotIn(item["answer"], prompts[0])
        self.assertNotIn(env["answer"], prompts[0])
        self.assertNotIn("ANSWER A:", prompts[0])

    def test_parser_accepts_one_fenced_object_after_explanatory_prose(self):
        payload = {"original_result": "18", "rewrite_result": "36", "same_question": True}
        parse = self.driver.module._referee_json
        self.assertEqual(parse(json.dumps(payload)), payload)
        self.assertEqual(parse("A: 18. B: 36.\n" + json.dumps(payload) + "\nDone."), payload)
        self.assertEqual(parse("I computed both answers.\n```json\n" + json.dumps(payload) + "\n```"), payload)

    def test_parser_refuses_ambiguous_or_nonobject_answers(self):
        parse = self.driver.module._referee_json
        for raw in ('{} {}', 'A: {} then B: {}', '[]', 'true', '```json\n{}\n```\n```json\n{}\n```',
                    '{}\n```json\n{}\n```', '```python\n{}\n```'):
            with self.subTest(raw=raw), self.assertRaises((ValueError, TypeError)):
                parse(raw)

    def test_replay_saved_sonnet_responses_without_network(self):
        transcript = ROOT / "runs" / "referee-sonnet46-blind-transcript.jsonl"
        if not transcript.exists():
            self.skipTest("local calibration transcript is not included")
        rows = [json.loads(line) for line in transcript.read_text().splitlines()]
        self.assertGreater(len(rows), 0)
        for row in rows:
            response = row["response"]["choices"][0]["message"]["content"]
            parsed = self.driver.module._referee_json(response)
            self.assertIn("original_result", parsed)
            self.assertIn("rewrite_result", parsed)


if __name__ == "__main__":
    unittest.main()
