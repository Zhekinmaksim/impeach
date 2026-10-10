import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
import population
from drivers import StubDriver


class NumericScoringTests(unittest.TestCase):
    def setUp(self):
        self.driver = StubDriver(population.World(population.load_corpus()))
        self.module = self.driver.module

    def test_canonical_decimal_preserves_value_exactly(self):
        for raw, value in [('00018.000', '18'), ('-0.000', '0'),
                           ('-001.2300', '-1.23'), ('0.10000000000000001', '0.10000000000000001')]:
            self.assertEqual(self.module.numeric_value(raw), value)

    def test_number_refuses_ambiguous_or_nondecimal_input(self):
        for raw in ['', '+18', '18 dollars', '1e3', '1,000', '.5', '5.', 'NaN', '∞', '١٨', '9' * 201]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.module.numeric_value(raw)

    def test_only_the_last_nonempty_answer_line_counts(self):
        self.assertEqual(self.module.numeric_line('Work: 10 + 8.\nANSWER: 0018.00\n\n'), '18')
        for raw in ['ANSWER: 18\nMore text', 'The answer is 18', 'ANSWER: 18 or 19', 'ANSWER: $18']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.module.numeric_line(raw)

    def test_frozen_numeric_rule_does_not_call_a_model_marker(self):
        claim = SimpleNamespace(prompt_template=json.dumps(population.TEMPLATE),
                                decode_params=json.dumps({'model':'test/subject'}),
                                endpoint='https://subject.invalid/v1/chat/completions',
                                scoring_rule=self.module.NUMERIC_LINE_RULE, subject='test/subject')
        def forbidden(_prompt):
            raise AssertionError('numeric grading must not call an LLM')
        self.driver.gl.nondet.handler = forbidden
        for reply, expected in [('Work\nANSWER: 0018.00', ('RIGHT','18')),
                                ('ANSWER: 19', ('WRONG','19')),
                                ('ANSWER: 18 dollars', ('WRONG',''))]:
            self.driver.gl.nondet.web.handler = lambda _url,_body: (200,json.dumps({'choices':[{'message':{'content':reply}}]}).encode())
            self.assertEqual(self.driver.contract._answer(claim,'What is 10 plus 8?','18'),expected)

    def test_structured_referee_object_is_accepted_without_text_cleanup(self):
        obj={'original_result':'18','rewrite_result':'36','same_question':True}
        self.assertEqual(self.module._referee_json(obj),obj)


if __name__ == '__main__':
    unittest.main()
