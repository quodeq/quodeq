"""Size ratchet: files <= 300 lines, functions <= 50 lines.

Baseline lists grandfathered violations. It may shrink, never grow.
"""
from tools.check_sizes import collect_violations, load_baseline

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 50


def test_no_new_size_violations():
    baseline = load_baseline()
    current = set(collect_violations())
    new = current - baseline
    assert not new, f"New size violations (split the file/function): {sorted(new)}"


def test_baseline_has_no_stale_entries():
    baseline = load_baseline()
    current = set(collect_violations())
    stale = baseline - current
    assert not stale, f"Fixed entries must be removed from size_baseline.txt: {sorted(stale)}"
