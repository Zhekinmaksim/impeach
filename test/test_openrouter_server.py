"""Offline request, concurrency and crash-accounting checks for the local gateway."""
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import openrouter_server as gateway
import rehearse

MODEL = "meta-llama/llama-3.1-8b-instruct"
PROVIDER = "deepinfra/fp8"
KEY = "fake-key-never-return"
REPLY = b'{ "choices": [{"message": {"content": "ANSWER: 18"}}] }'


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "budget.sqlite"
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def upstream(self, key, body):
        self.calls.append((key, body))
        return 200, REPLY

    def app(self, budget="0.01", upstream=None):
        return gateway.Gateway(MODEL, PROVIDER, KEY, budget, self.path, upstream or self.upstream)

    def request(self):
        return gateway.canonical(gateway.trial_requests(MODEL)[0]).encode()

    def test_real_contract_parity_all_72(self):
        seen = []

        def http(url, body):
            seen.append(json.loads(body))
            return 200, REPLY

        rehearse.run_rehearsal(rehearse.load_claim(str(ROOT / "calibration/claim-gsm8k.json")), MODEL, 0, http)
        self.assertEqual(len(seen), 72)
        self.assertEqual({gateway.canonical(b) for b in seen}, {gateway.canonical(b) for b in gateway.trial_requests(MODEL)})

    def test_replay_spends_each_time_and_response_unchanged(self):
        app = self.app()
        for _ in range(3):
            self.assertEqual(app.complete(self.request()), (200, REPLY))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(app.ledger.remaining(), 7000)
        key, sent = self.calls[0]
        self.assertEqual(key, KEY)
        self.assertEqual(sent["provider"], {"only": [PROVIDER], "allow_fallbacks": False,
            "require_parameters": True, "max_price": {"prompt": 0.05, "completion": 0.1, "request": 0}})
        without_provider = dict(sent)
        del without_provider["provider"]
        self.assertEqual(without_provider, json.loads(self.request()))

    def test_invalid_requests_never_reserve_or_fetch(self):
        app = self.app()
        for changes in [
            {"model": "other/model"}, {"messages": [{"role": "user", "content": "hello"}]},
            {"max_tokens": 100000}, {"seed": 8}, {"tools": []}, {"stream": True},
            {"provider": {"only": ["expensive"]}}, {"temperature": True},
        ]:
            body = dict(json.loads(self.request()), **changes)
            self.assertEqual(app.complete(gateway.canonical(body).encode())[0], 403)
        self.assertEqual(app.complete(b"{")[0], 400)
        self.assertEqual(app.complete(b"x" * (gateway.MAX_BODY + 1))[0], 413)
        self.assertEqual(app.ledger.remaining(), 10000)
        self.assertEqual(self.calls, [])

    def test_concurrent_requests_cannot_overspend(self):
        app = self.app("0.007")
        with ThreadPoolExecutor(max_workers=20) as pool:
            statuses = list(pool.map(lambda _: app.complete(self.request())[0], range(40)))
        self.assertEqual(statuses.count(200), 7)
        self.assertEqual(statuses.count(503), 33)
        self.assertEqual(len(self.calls), 7)
        self.assertEqual(app.ledger.remaining(), 0)

    def test_restart_preserves_budget_and_rejects_reset(self):
        first = self.app("0.002")
        self.assertEqual(first.complete(self.request())[0], 200)
        second = self.app("0.002")
        self.assertEqual(second.ledger.remaining(), 1000)
        self.assertEqual(second.complete(self.request())[0], 200)
        self.assertEqual(self.app("0.002").complete(self.request())[0], 503)
        with self.assertRaises(ValueError):
            self.app("0.003")
        with self.assertRaises(ValueError):
            gateway.BudgetLedger(self.path, "0.002", "different-trial")

    def test_failures_keep_reservations_and_never_expose_keys(self):
        def failed(key, body):
            raise RuntimeError(KEY)
        app = self.app("0.002", failed)
        status, body = app.complete(self.request())
        self.assertEqual(status, 502)
        self.assertNotIn(KEY.encode(), body)
        self.assertEqual(app.ledger.remaining(), 1000)
        # A process killed after this committed reservation also leaves it charged.
        self.assertTrue(app.ledger.reserve(1000))
        self.assertEqual(self.app("0.002").complete(self.request())[0], 503)

    def test_worst_case_reservation_and_input_budget_validation(self):
        for body in gateway.trial_requests(MODEL):
            amount = gateway.reservation_micros(body)
            cost_micros = (len(gateway.canonical(body).encode()) + 1024) * .05 + body["max_tokens"] * .1
            self.assertGreaterEqual(amount, cost_micros * 1.1)
            self.assertGreaterEqual(amount, 1000)
        large = {"messages": [{"role": "user", "content": "x" * 24000}], "max_tokens": 4096}
        self.assertGreater(gateway.reservation_micros(large), 1000)
        for budget in ("0", "-1", "5.01", "Infinity", "0.0000001"):
            with self.assertRaises(ValueError):
                gateway.BudgetLedger(Path(self.tmp.name) / (budget + ".sqlite"), budget, "test")


if __name__ == "__main__":
    unittest.main()
