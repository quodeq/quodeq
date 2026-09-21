#!/usr/bin/env python3
"""Dead-code ratchet: flag definitions nothing references (M-ANA-10).

Ruff's F401/F841 only see a single scope: an import nobody uses, a local
nobody reads. A function, method, class or module constant that no longer
has a caller is invisible to them and stays in the tree, where it costs
every reader who has to work out whether it matters. vulture closes that
gap by collecting every definition and every name used anywhere, then
reporting the difference.

vulture works by name, not by resolution, so it has false positives: a
name reached dynamically (a pytest fixture, a Flask route, an ABC hook, an
`__all__` re-export) has no static reference. Those go in
tools/vulture_whitelist.py with a one-line reason, never here.

Existing reports are grandfathered in tools/dead_code_baseline.txt so the
gate runs green today while preventing NEW dead code. Regenerate the
baseline (only with justification) via:
    python tools/check_dead_code.py --update-baseline

Scans src/quodeq plus the whitelist at `--min-confidence 60`, the level
below which vulture's own docs call the reports noise. 60 rather than 80
on purpose: at 80 vulture reports only unused local variables and
unreachable code (three in this tree), which is exactly the part ruff
already covers, and none of the unreferenced functions and methods this
gate exists for.

Entries are line-keyed (relpath:lineno:name), so an unrelated line-count
change above a grandfathered report shifts its entry. Prefer hand-editing
the baseline over blind --update-baseline regeneration, which can silently
absorb genuinely new dead code introduced in the same change.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import _ratchet

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "dead_code_baseline.txt"

# src/quodeq is the scanned tree; the whitelist is passed alongside it so
# the names it references count as used. tests/ and tools/ are out of
# scope: a test helper's only caller is often the test collector, and a
# tool is a standalone script.
SCAN_PATHS = ("src/quodeq", "tools/vulture_whitelist.py")
MIN_CONFIDENCE = 60

# `path:line: unused <kind> '<name>' (N% confidence)`, vulture's one report
# per line. `<kind>` is one or two words (variable, function, method,
# class, property, attribute, import, "class attribute").
_REPORT = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): unused (?P<kind>[a-z ]+?) "
    r"'(?P<name>[^']+)' \((?P<confidence>\d+)% confidence\)$"
)


@dataclass(frozen=True, slots=True)
class Hit:
    """One vulture report: what is unused, where, and how sure vulture is."""

    path: str
    line: int
    kind: str
    name: str
    confidence: int

    @property
    def key(self) -> str:
        """Identity for a report: relpath:lineno:name."""
        return f"{self.path}:{self.line}:{self.name}"


def parse_report(output: str) -> list[Hit]:
    """Parse vulture's stdout into hits, warning about lines it cannot read.

    A line that does not match is never dropped silently: vulture also
    emits `unreachable code after ...` reports, which carry no name and so
    cannot be keyed, and a future version may add a shape this gate has
    not seen.
    """
    hits: list[Hit] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        m = _REPORT.match(line.strip())
        if m is None:
            print(f"warning: unparsed vulture report: {line}", file=sys.stderr)
            continue
        hits.append(Hit(
            path=m["path"].replace("\\", "/"),
            line=int(m["line"]),
            kind=m["kind"],
            name=m["name"],
            confidence=int(m["confidence"]),
        ))
    return hits


def run_vulture(root: Path = REPO_ROOT) -> str:
    """Run vulture over SCAN_PATHS and return its stdout.

    Equivalent to `uv run vulture src/quodeq tools/vulture_whitelist.py
    --min-confidence 60`; spelled `-m vulture` so the gate uses the
    interpreter it is already running under. Exit code 3 means "reports
    found", not a failure; anything else with output on stderr is.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "vulture", *SCAN_PATHS,
         "--min-confidence", str(MIN_CONFIDENCE)],
        cwd=root, capture_output=True, text=True, timeout=300, check=False,
    )
    if proc.returncode not in (0, 3):
        raise RuntimeError(
            f"vulture exited {proc.returncode}:\n{proc.stdout}{proc.stderr}"
        )
    return proc.stdout


def _scan() -> list[Hit]:
    """Return every vulture report in src/quodeq, sorted by key."""
    return sorted(parse_report(run_vulture()), key=violation_key)


def violation_key(hit: Hit) -> str:
    """Identity for a report: relpath:lineno:name."""
    return hit.key


def describe(hit: Hit) -> str:
    """One-line report of an unused definition."""
    return f"{hit.key}: unused {hit.kind} ({hit.confidence}% confidence)"


def collect_violations() -> list[str]:
    """Return baseline keys for all current vulture reports."""
    return sorted({violation_key(hit) for hit in _scan()})


def load_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """Return the set of grandfathered dead-code keys (empty if no baseline)."""
    return _ratchet.load_baseline(path)


def write_baseline(path: Path = BASELINE_PATH) -> int:
    """Write current vulture reports to the baseline file; return the count."""
    header = (
        "# Grandfathered dead code (vulture reports over src/quodeq at\n"
        "# --min-confidence 60). Do NOT add entries without justification --\n"
        "# the goal is to burn this list to zero, not grow it.\n"
        "# The fix is to delete the definition, once a grep over src, tests,\n"
        "# tools, CI and docs shows nothing references it (a name a test\n"
        "# patches by string is NOT dead). A name reached dynamically is a\n"
        "# false positive and belongs in tools/vulture_whitelist.py with a\n"
        "# reason, not here.\n"
        "# Regenerate intentionally: python tools/check_dead_code.py --update-baseline\n"
        "# Entries are line-keyed (relpath:lineno:name), so an unrelated\n"
        "# line-count change above a grandfathered report shifts its entry.\n"
        "# Prefer hand-editing the baseline over blind regeneration, which can\n"
        "# silently absorb genuinely new dead code added in the same change.\n"
    )
    return _ratchet.write_baseline(path, header, collect_violations())


def main(argv: list[str] | None = None) -> int:
    """Run the ratchet CLI: `check_dead_code.py [--update-baseline]`."""
    return _ratchet.run_cli(argv, _ratchet.RatchetSpec(
        script_name="check_dead_code.py",
        noun="dead-code",
        baseline_path=BASELINE_PATH,
        scan=_scan,
        violation_key=violation_key,
        update_baseline=write_baseline,
        describe=describe,
    ))


if __name__ == "__main__":
    sys.exit(main())
