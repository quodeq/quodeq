#!/usr/bin/env python3
"""Private-import ratchet: flag imports that reach into another package's
private names/modules (rule A/B, see tools/_private_imports_rules.py) and,
for src/quodeq, the stricter rules 2-4 (tools/_private_imports_strict.py):
no `_name` imported from another file, none listed in `__all__`, and no
`mod._x` read through a module alias.

Existing violations are grandfathered via two baselines so the gate runs
green today while preventing NEW ones:
  - tools/private_imports_baseline.txt for src/quodeq (target: zero)
  - tools/private_imports_tests_baseline.txt for tests (ratchet only; a test
    file can never be "the same package" as the src it exercises, so this
    baseline is expected to stay large -- it must not grow)
Regenerate both (only with justification) via:
    python tools/check_private_imports.py --update-baseline

Scans src/quodeq/**/*.py and tests/**/*.py with `ast` (vendored/generated
dirs excluded, see tools/_ratchet.py:EXCLUDE_DIRS); tools/ is out of scope.
Entries are line-keyed (relpath:lineno:kind:module.name), so an unrelated
line-count change above a grandfathered import shifts its entry. Prefer
hand-editing a baseline over blind --update-baseline regeneration, which can
silently absorb a genuinely new violation introduced in the same change.
"""
from __future__ import annotations

import sys
from pathlib import Path

import _ratchet
from _private_imports_rules import Hit, scan_tree
from _private_imports_strict import strict_hits

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "quodeq"
TESTS_ROOT = REPO_ROOT / "tests"
SRC_BASELINE_PATH = Path(__file__).resolve().parent / "private_imports_baseline.txt"
TESTS_BASELINE_PATH = Path(__file__).resolve().parent / "private_imports_tests_baseline.txt"

_SRC_HEADER = (
    "# Grandfathered private-import violations in src/quodeq (rules A/B and 2-4,\n"
    "# see tools/check_private_imports.py). Do NOT add entries without justification\n"
    "# -- the goal is to burn this list to ZERO, not grow it.\n"
    "# Regenerate intentionally: python tools/check_private_imports.py --update-baseline\n"
    "# Entries are line-keyed (relpath:lineno:kind:module.name), so an unrelated\n"
    "# line-count change above a grandfathered import shifts its entry. Prefer\n"
    "# hand-editing the baseline over blind --update-baseline regeneration, which\n"
    "# can silently absorb a genuinely new violation introduced in the same change.\n"
)
_TESTS_HEADER = (
    "# Grandfathered private-import violations in tests/ (rule A/B, see\n"
    "# tools/_private_imports_rules.py). A test file can never be \"the same\n"
    "# package\" as the src it exercises, so this list is expected to stay\n"
    "# large -- it is a ratchet (must not grow), not a to-zero gate.\n"
    "# Regenerate intentionally: python tools/check_private_imports.py --update-baseline\n"
)


def _scan_src() -> list[Hit]:
    """Return all current rule A/B and 2-4 violations under src/quodeq."""
    return scan_tree(SRC_ROOT, SRC_ROOT, REPO_ROOT, extra=strict_hits)


def _scan_tests() -> list[Hit]:
    """Return all current rule A/B violations under tests/."""
    return scan_tree(TESTS_ROOT, SRC_ROOT, REPO_ROOT)


def violation_key(hit: Hit) -> str:
    """Identity for a violation: relpath:lineno:kind:module.name."""
    return hit.key


def describe(hit: Hit) -> str:
    """One-line report of a violation, with the offending source line."""
    return f"{hit.key}: {hit.source}"


def collect_src_violations() -> list[str]:
    """Return baseline keys for all current src/quodeq violations."""
    return sorted({violation_key(hit) for hit in _scan_src()})


def collect_tests_violations() -> list[str]:
    """Return baseline keys for all current tests/ violations."""
    return sorted({violation_key(hit) for hit in _scan_tests()})


def write_src_baseline(path: Path = SRC_BASELINE_PATH) -> int:
    """Write current src/quodeq violations to the baseline; return the count."""
    return _ratchet.write_baseline(path, _SRC_HEADER, collect_src_violations())


def write_tests_baseline(path: Path = TESTS_BASELINE_PATH) -> int:
    """Write current tests/ violations to the baseline; return the count."""
    return _ratchet.write_baseline(path, _TESTS_HEADER, collect_tests_violations())


def _specs() -> tuple[_ratchet.RatchetSpec[Hit], _ratchet.RatchetSpec[Hit]]:
    src_spec = _ratchet.RatchetSpec(
        script_name="check_private_imports.py",
        noun="private-import (src)",
        baseline_path=SRC_BASELINE_PATH,
        scan=_scan_src,
        violation_key=violation_key,
        update_baseline=write_src_baseline,
        describe=describe,
    )
    tests_spec = _ratchet.RatchetSpec(
        script_name="check_private_imports.py",
        noun="private-import (tests)",
        baseline_path=TESTS_BASELINE_PATH,
        scan=_scan_tests,
        violation_key=violation_key,
        update_baseline=write_tests_baseline,
        describe=describe,
    )
    return src_spec, tests_spec


def main(argv: list[str] | None = None) -> int:
    """Run both ratchets (src to zero, tests non-growing); worst code wins."""
    args = list(argv) if argv is not None else sys.argv[1:]
    src_spec, tests_spec = _specs()
    return max(_ratchet.run_cli(args, src_spec), _ratchet.run_cli(args, tests_spec))


if __name__ == "__main__":
    sys.exit(main())
