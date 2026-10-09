#!/usr/bin/env python3
"""The same scenarios, on the real SDK.

Loads contracts/impeach.py through genlayer-test's direct mode, against the
exact `py-genlayer` runner hash pinned in the contract header. Typed storage,
calldata round-trips and the eq-principle wrappers are the real ones. The
endpoint and the LLM are still scripted: nothing here touches a network after
the one-time download of the GenVM release.

    pip install genlayer-test
    python3 test/run_sdk.py

Set IMPEACH_GENVM to pick the GenVM release the runner is extracted from.
"""

import os
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))

try:
    import gltest.direct  # noqa: F401
except ImportError:
    print("genlayer-test is required for the SDK check (pip install -r requirements-dev.txt)")
    raise SystemExit(1)

warnings.filterwarnings("ignore", category=RuntimeWarning)

import population as pop  # noqa: E402
import scenarios  # noqa: E402
from drivers import SdkDriver  # noqa: E402


def make():
    world = pop.World(scenarios.CORPUS)
    return SdkDriver(world), world


def main() -> int:
    quiet = "--quiet" in sys.argv
    check = scenarios.run_all(make, "sdk", module=None, quiet=quiet)
    print("\n%d passed, %d failed  (pinned SDK, GenVM %s)" % (len(check.passed), len(check.failed), SdkDriver.SDK_VERSION))
    for name in check.failed:
        print("  FAIL " + name)
    return 1 if check.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
