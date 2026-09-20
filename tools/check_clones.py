#!/usr/bin/env python3
"""Clone ratchet: flag NEW copy-paste duplication in Python and UI sources.

Duplication is what the self-eval keeps charging maintainability for: the
same fragment edited in one copy and forgotten in the other. The fix is a
shared helper (in `core/`, `shared/`, `utils/` or the feature's helper
module), never a third copy.

Detection is jscpd, configured once in `.jscpd.json` at the repo root
(5 lines / 50 tokens, formats python+javascript+jsx, tests, snapshots,
fixtures, node_modules and dist excluded). jscpd is a devDependency of the
UI package, so it runs from `src/quodeq/ui` via `npx --no-install`; if it
is missing the gate says how to install it instead of passing silently.

Existing clones are grandfathered in tools/clones_baseline.txt so the gate
runs green today while preventing NEW ones. Regenerate (only with
justification) via:
    python tools/check_clones.py --update-baseline

Entries are span-keyed (`fileA:start-end|fileB:start-end`, repo-relative,
pair sorted), so editing above a grandfathered clone shifts its entry and
the gate reports it as new. That is the intended prompt to extract the
helper; regenerate only when the move is deliberate, because a blind
--update-baseline can absorb a genuinely new clone from the same change.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import _clones_rules
import _ratchet
from _clones_rules import Clone

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "clones_baseline.txt"

_HEADER = (
    "# Grandfathered clones (jscpd, see .jscpd.json: 5 lines / 50 tokens).\n"
    "# Do NOT add entries without justification -- the goal is to burn this\n"
    "# list to zero by extracting shared helpers, not to grow it.\n"
    "# Regenerate intentionally: python tools/check_clones.py --update-baseline\n"
    "# Entries are span-keyed (fileA:start-end|fileB:start-end, repo-relative,\n"
    "# pair sorted), so an edit above a grandfathered clone shifts its entry.\n"
    "# Prefer hand-editing this file over blind --update-baseline regeneration,\n"
    "# which can silently absorb a genuinely new clone from the same change.\n"
)


def scan_tree(repo_root: Path = REPO_ROOT) -> list[Clone]:
    """Run jscpd over *repo_root* and return its clones, sorted by key."""
    with tempfile.TemporaryDirectory(prefix="jscpd-") as tmp:
        payload = _clones_rules.run_jscpd(repo_root, Path(tmp))
        return _clones_rules.parse_report(payload, _clones_rules.ui_dir(repo_root), repo_root)


def _scan() -> list[Clone]:
    """Return every clone in the current tree."""
    return scan_tree()


def violation_key(clone: Clone) -> str:
    """Identity for a clone: fileA:start-end|fileB:start-end."""
    return clone.key


def describe(clone: Clone) -> str:
    """One-line report of a clone, with its format and size."""
    return f"{clone.key} ({clone.lines} lines, {clone.fmt})"


def collect_violations() -> list[str]:
    """Return baseline keys for all current clones."""
    return sorted({violation_key(clone) for clone in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the set of grandfathered clone keys (empty if no baseline)."""
    return _ratchet.load_baseline(path)


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write the current clones to the baseline file; return the count."""
    return _ratchet.write_baseline(path, _HEADER, collect_violations())


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet CLI: `check_clones.py [--update-baseline]`."""
    spec = _ratchet.RatchetSpec(
        script_name="check_clones.py",
        noun="clone",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=lambda: write_baseline(BASELINE_PATH),
        describe=describe,
    )
    try:
        return _ratchet.run_cli(argv, spec)
    except _clones_rules.JscpdUnavailable as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
