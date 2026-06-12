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


def test_baseline_has_no_stale_entries():
    """Fixing a violation must shrink the baseline, keeping it honest."""
    current = {check_imports.violation_key(v) for v in check_imports.collect_violations()}
    stale = sorted(check_imports.load_baseline() - current)
    assert stale == [], (
        "Baseline lists violations that no longer exist; regenerate with "
        "`python tools/check_imports.py --update-baseline`:\n" + "\n".join(stale)
    )
