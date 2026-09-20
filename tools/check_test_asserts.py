#!/usr/bin/env python3
"""Assertion ratchet: flag NEW tests that assert more than 8 things.

A test with a dozen assertions stops at the first failure and hides the
rest, and its name can only describe one of the behaviours it checks. The
fix is a split: one behaviour per test, sharing the fixture.

Counts per test:
  - Python (`tests/**/*.py`, via `ast`): `assert` statements, plus each
    `with pytest.raises(...)` item as one assertion.
  - JS (`src/quodeq/ui/src/**/*.test.{js,jsx}`): `expect(` calls inside
    each `it()`/`test()` body, found by balancing the call's parentheses
    over a copy of the source with comments and string bodies blanked out
    (see tools/_test_asserts_rules.py).

Existing over-asserting tests are grandfathered in
tools/test_asserts_baseline.txt so the gate runs green today while
preventing NEW ones. Regenerate (only with justification) via:
    python tools/check_test_asserts.py --update-baseline

Entries are keyed `relpath:test_name` (a method keeps its class, e.g.
`Class.test_x`), so they survive edits above the test; renaming a
grandfathered test reports it as new, which is the moment to split it
rather than re-baseline. Because the key has no count in it, a
grandfathered test that grows further is not re-reported -- the gate
blocks new offenders, the baseline ceiling in the test file blocks growth
in number.
"""
from __future__ import annotations

import sys
from pathlib import Path

import _ratchet
from _test_asserts_rules import MAX_ASSERTIONS, TestCase, over_limit, scan_tree

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "test_asserts_baseline.txt"

_HEADER = (
    f"# Grandfathered tests asserting more than {MAX_ASSERTIONS} things (Python\n"
    "# `assert`/`pytest.raises`, JS `expect(` per `it()`). Do NOT add entries\n"
    "# without justification -- the goal is to burn this list to zero by\n"
    "# splitting tests, one behaviour per test, not to grow it.\n"
    "# Regenerate intentionally: python tools/check_test_asserts.py --update-baseline\n"
    "# Entries are keyed relpath:test_name (a method keeps its class).\n"
)


def _scan() -> list[TestCase]:
    """Return every test over the assertion limit, sorted by key."""
    return over_limit(scan_tree(REPO_ROOT))


def violation_key(case: TestCase) -> str:
    """Identity for a violation: relpath:test_name."""
    return case.key


def describe(case: TestCase) -> str:
    """One-line report of a test and how many assertions it makes."""
    return f"{case.key}: {case.count} assertions (line {case.line})"


def collect_violations() -> list[str]:
    """Return baseline keys for all current over-asserting tests."""
    return sorted({violation_key(case) for case in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the set of grandfathered test keys (empty if no baseline)."""
    return _ratchet.load_baseline(path)


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write the current over-asserting tests to the baseline; return the count."""
    return _ratchet.write_baseline(path, _HEADER, collect_violations())


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet CLI: `check_test_asserts.py [--update-baseline]`."""
    return _ratchet.run_cli(argv, _ratchet.RatchetSpec(
        script_name="check_test_asserts.py",
        noun="assertions-per-test",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=lambda: write_baseline(BASELINE_PATH),
        describe=describe,
    ))


if __name__ == "__main__":
    sys.exit(main())
