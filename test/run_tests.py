#!/usr/bin/env python3
"""Offline end to end run. No network, no Bradbury, no dependencies.

    python3 test/run_tests.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))

import population as pop  # noqa: E402
import scenarios  # noqa: E402
from drivers import StubDriver  # noqa: E402


def make():
    world = pop.World(scenarios.CORPUS)
    return StubDriver(world), world


def main() -> int:
    probe, _ = make()
    check = scenarios.run_all(make, "stub", module=probe.module)
    print("\n%d passed, %d failed  (local stub)" % (len(check.passed), len(check.failed)))
    for name in check.failed:
        print("  FAIL " + name)
    return 1 if check.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
