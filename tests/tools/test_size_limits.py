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


def test_tests_tree_is_scanned_at_file_level():
    from tools.check_sizes import _scan_tests
    keys = {f"{rel}:{lineno}:{kind}" for rel, lineno, kind, _size in _scan_tests()}
    # Known oversized test file on develop b3bcd174 (921 lines); if it has
    # been split since, pick any tests/**/*.py over 300 lines instead.
    assert "tests/api/test_assistant_routes.py:1:file" in keys
    assert all(k.endswith(":1:file") for k in keys), "tests/ is file-level only"


# Revise DOWNWARD as size workstreams burn entries; NEVER raise without a
# justification reviewed in the PR that raises it.
BASELINE_CEILING = 74  # set to the count --update-baseline printed in Task 2 step 3


def test_baseline_only_shrinks():
    count = len(load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Split the new file/function instead of grandfathering it. If growth is "
        "truly justified, raise BASELINE_CEILING in the same PR and explain why."
    )
