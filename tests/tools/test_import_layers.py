"""Layer-import gate: fail the build on NEW violations beyond the baseline."""
from __future__ import annotations

import check_imports


def test_no_new_import_violations():
    baseline = check_imports.load_baseline()
    new = [
        v for v in check_imports.collect_violations()
        if check_imports.violation_key(v) not in baseline
    ]
    assert new == [], (
        "New layer-import violation(s) introduced. Fix the import, or only "
        "with justification run `python tools/check_imports.py --update-baseline`:\n"
        + "\n".join(check_imports.violation_key(v) for v in new)
        + "\nIf test_baseline_has_no_stale_entries also fails for the same "
        "file and target, you only shifted lines above a grandfathered "
        "import; regenerating the baseline is the correct fix."
    )


# Revise DOWNWARD as clean-architecture workstreams burn entries; NEVER raise
# without a justification reviewed in the PR that raises it.
BASELINE_CEILING = 34


def test_baseline_only_shrinks():
    """The grandfathered list is a burn-down list, not a dumping ground."""
    count = len(check_imports.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Fix the new import instead of grandfathering it. If growth is truly "
        "justified, raise BASELINE_CEILING in the same PR and explain why."
    )


def test_baseline_has_no_stale_entries():
    """Fixing a violation must shrink the baseline, keeping it honest."""
    current = {check_imports.violation_key(v) for v in check_imports.collect_violations()}
    stale = sorted(check_imports.load_baseline() - current)
    assert stale == [], (
        "Baseline lists violations that no longer exist; regenerate with "
        "`python tools/check_imports.py --update-baseline`:\n" + "\n".join(stale)
    )
