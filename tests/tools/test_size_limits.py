"""Size ratchet: files <= 300 lines, functions <= 50 lines.

Baseline lists grandfathered violations. It may shrink, never grow.
"""
import check_sizes

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 50


def test_no_new_size_violations():
    baseline = check_sizes.load_baseline()
    current = set(check_sizes.collect_violations())
    new = current - baseline
    assert not new, f"New size violations (split the file/function): {sorted(new)}"


def test_baseline_has_no_stale_entries():
    baseline = check_sizes.load_baseline()
    current = set(check_sizes.collect_violations())
    stale = baseline - current
    assert not stale, f"Fixed entries must be removed from size_baseline.txt: {sorted(stale)}"


def test_tests_tree_is_scanned_at_file_level():
    keys = {f"{rel}:{lineno}:{kind}" for rel, lineno, kind, _size in check_sizes._scan_tests()}
    tests_keys = {k for k in check_sizes.load_baseline() if k.startswith("tests/")}
    assert tests_keys and tests_keys <= keys, "tests/ tree is not being scanned"
    assert all(k.endswith(":1:file") for k in keys), "tests/ is file-level only"


# Revise DOWNWARD as size workstreams burn entries; NEVER raise without a
# justification reviewed in the PR that raises it.
BASELINE_CEILING = 72  # set to the count --update-baseline printed; lower it as entries burn down


def test_baseline_only_shrinks():
    count = len(check_sizes.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Split the new file/function instead of grandfathering it. If growth is "
        "truly justified, raise BASELINE_CEILING in the same PR and explain why."
    )
