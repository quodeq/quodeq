"""Ratchet: no new refactor narration in the prose of src/quodeq and tests.

"Split from cli_evaluation.py to keep each module under 300 lines",
"Extracted verbatim", "facade patch targets" or "moved here from" describe
the edit that produced the code, not the code. The next reader learns
nothing about what the module does, and the evaluator reports each one as
an analyzability finding. The fix is to say what the module or symbol is
for; the history lives in git.

Scoped to comment and docstring text like the planning-label gate, and
sharing its prose extractors. Existing sites are grandfathered in
tools/refactor_narration_baseline.txt, which may only shrink. Regenerate it
only after a sweep that removed sites:

    PYTHONPATH=. python tests/tools/test_no_refactor_narration.py --update-baseline
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from tests.tools.test_no_planning_labels import REPO, iter_sources, js_prose, python_prose

BASELINE = REPO / "tools" / "refactor_narration_baseline.txt"
_HEADER = (
    "# Grandfathered refactor-narration sites (path:line). May only shrink.\n"
    "# Regenerate: PYTHONPATH=. python tests/tools/test_no_refactor_narration.py --update-baseline\n"
)

SHAPES = (
    r"\bSplit (?:out )?(?:from|of)\b",              # Split from x.py / Split out of y.jsx
    r"\b[Ee]xtracted verbatim\b",                    # Extracted verbatim.
    r"\bto keep (?:each|the|this|that) (?:module|file)s? under\b",  # ... under 300 lines
    r"\bunder the size ratchet\b",
    r"\bfacade patch targets?\b",                    # imports kept so tests can patch
    r"\bso (?:the )?tests? can patch\b",
    r"\b[Mm]oved (?:out )?from\b|\bmoved here from\b",
)
NARRATION = re.compile("|".join(f"(?:{shape})" for shape in SHAPES))


def narration_in(text: str) -> list[str]:
    """Every narration phrase in one piece of prose."""
    return [match.group(0) for match in NARRATION.finditer(text)]


def collect_sites() -> list[str]:
    """Return `path:line` for every narration phrase in scoped prose."""
    sites: list[str] = []
    this_file = Path(__file__).resolve()
    for path in iter_sources():
        if path == this_file:  # the docstring above quotes the shapes it bans
            continue
        source = path.read_text(encoding="utf-8")
        extract = python_prose if path.suffix == ".py" else js_prose
        for lineno, text in extract(source):
            for match in NARRATION.finditer(text):
                at = lineno + text[:match.start()].count("\n")
                sites.append(f"{path.relative_to(REPO)}:{at}")
    return sites


def load_baseline() -> set[str]:
    """Grandfathered keys, empty when the file is missing."""
    if not BASELINE.exists():
        return set()
    return {
        line.strip() for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def update_baseline() -> int:
    """Rewrite the baseline from the current tree; return the count."""
    keys = sorted(set(collect_sites()))
    BASELINE.write_text(_HEADER + "\n".join(keys) + ("\n" if keys else ""), encoding="utf-8")
    return len(keys)


def test_no_new_refactor_narration():
    new = sorted(set(collect_sites()) - load_baseline())
    assert new == [], (
        "Refactor narration in comments or docstrings (\"Split from\", \"Extracted "
        "verbatim\", \"to keep the module under N lines\", \"facade patch targets\", "
        "\"moved from\"). Say what the code is for; the history lives in git. If an "
        "edit only moved a grandfathered site, hand-edit its line number in "
        "tools/refactor_narration_baseline.txt instead of regenerating:\n" + "\n".join(new)
    )


def test_baseline_has_no_stale_entries():
    stale = sorted(load_baseline() - set(collect_sites()))
    assert stale == [], (
        "Stale entries in tools/refactor_narration_baseline.txt. If the site was "
        "fixed, remove the entry; if an edit above it shifted its line, hand-edit "
        "the line number:\n" + "\n".join(stale)
    )


# Revise DOWNWARD as sites are rewritten; NEVER raise without a justification
# reviewed in the PR that raises it.
BASELINE_CEILING = 291  # the tree on 2026-09-26, before any sweep


def test_baseline_only_shrinks():
    count = len(load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). Rewrite the "
        "narration instead of grandfathering it."
    )


def test_shapes_match_narration_and_not_ordinary_prose():
    positives = (
        "Split from ``cli_evaluation.py`` to keep each module under 300 lines.",
        " * Split out of ComparePage.test.jsx.",
        "session tab strip. Extracted verbatim.",
        "kept under the size ratchet; the rest",
        "from x import y  # noqa: F401 -- facade patch targets",
        "# imports kept so tests can patch them",
        "# Re-exported: moved from _cli_worktree.py",
    )
    negatives = (
        "the finding's own req verbatim.",
        "should pass through verbatim",
        "split the string on commas",
        "A file at the size cap; see check_sizes.",
        "the patch target is the facade module",
    )
    assert all(narration_in(text) for text in positives), [
        text for text in positives if not narration_in(text)
    ]
    assert not any(narration_in(text) for text in negatives), [
        text for text in negatives if narration_in(text)
    ]


if __name__ == "__main__":
    if sys.argv[1:] == ["--update-baseline"]:
        print(f"Wrote {update_baseline()} site(s) to {BASELINE.relative_to(Path.cwd())}")
    else:
        print(f"Usage: {Path(__file__).name} --update-baseline")
