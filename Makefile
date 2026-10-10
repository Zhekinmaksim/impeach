PY ?= python3
MANIFEST ?= runs/bradbury.jsonl
RPC ?= https://rpc-bradbury.genlayer.com

.PHONY: check check-sdk lint snapshot publish assets serve clean

# Everything that needs no network and no dependencies. This is what CI runs.
check: lint
	$(PY) test/run_tests.py
	$(PY) -m unittest discover -s test -p 'test_*.py'
	$(PY) scripts/make_fixtures.py --check
	node test/test_parity.mjs
	node --test test/test_gas.mjs
	node --test test/test_proxy.mjs
	$(PY) cli/impeach.py recompute web/case.json

# The same scenarios on the real SDK at the runner hash pinned in the contract.
# Needs `pip install genlayer-test` and one download of the GenVM release.
check-sdk:
	$(PY) test/run_sdk.py --quiet

lint:
	$(PY) cli/impeach.py envelope examples/rewrites/*.json --items calibration/gsm8k-24.items.json > /dev/null && echo "rewrites ok"

# A rehearsal snapshot. Never overwrite a live snapshot with this one.
snapshot:
	$(PY) scripts/simulate.py --out web/case.json
	$(PY) scripts/make_fixtures.py

# Rebuild the published snapshot from settled receipts. collect exits non-zero
# when nothing has settled, and make stops there.
publish:
	$(PY) scripts/collect.py $(MANIFEST) --address $(CONTRACT) --rpc $(RPC) --out web/case.json
	$(PY) cli/impeach.py recompute web/case.json

# Logo, share card and icons. Needs fonttools, brotli, uharfbuzz, playwright and
# pillow; outputs are committed.
assets:
	$(PY) scripts/make_logo.py
	$(PY) scripts/make_assets.py

serve:
	$(PY) -m http.server -d web 8000

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
