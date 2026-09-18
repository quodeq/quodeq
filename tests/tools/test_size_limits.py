"""Size ratchet: files <= 300 lines, functions <= 60 lines.

Baseline lists grandfathered violations. It may shrink, never grow.
"""
from pathlib import Path

import _ratchet
import check_sizes

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 60


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


def test_tests_tree_is_scanned_at_file_level(tmp_path, monkeypatch):
    """The walk reaches tests/, and reports it by file only, never by function.

    Asserted against the walk itself rather than against baseline entries:
    the baseline is empty, so real violations can no longer prove coverage.
    """
    walked = {p.resolve() for p in _ratchet.iter_python_files(check_sizes.TESTS_ROOT)}
    assert Path(__file__).resolve() in walked, "tests/ tree is not being scanned"

    oversized = tmp_path / "tests" / "test_oversized.py"
    oversized.parent.mkdir()
    body = "def test_x():\n" + "    assert True\n" * check_sizes.MAX_FILE_LINES
    oversized.write_text(body, encoding="utf-8")
    monkeypatch.setattr(check_sizes, "TESTS_ROOT", oversized.parent)
    monkeypatch.setattr(check_sizes, "REPO_ROOT", tmp_path)

    found = check_sizes._scan_tests()
    assert [(rel, lineno, kind) for rel, lineno, kind, _size in found] == [
        ("tests/test_oversized.py", 1, "file"),
    ], "tests/ is file-level only"


# Revise DOWNWARD as size workstreams burn entries; NEVER raise without a
# justification reviewed in the PR that raises it.
BASELINE_CEILING = 0  # set to the count --update-baseline printed; lower it as entries burn down


def test_baseline_only_shrinks():
    count = len(check_sizes.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Split the new file/function instead of grandfathering it. If growth is "
        "truly justified, raise BASELINE_CEILING in the same PR and explain why."
    )
