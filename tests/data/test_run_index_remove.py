"""_remove_run_directory path guards: traversal and absolute run ids never reach rmtree."""
from __future__ import annotations

from pathlib import Path

from quodeq.services._run_index_fs import _remove_run_directory


def test_remove_run_directory_rejects_path_traversal_in_run_uuid(tmp_path: Path):
    """Path traversal in run_uuid must not reach rmtree.

    A malicious run_uuid like "../../../etc/passwd" must be rejected before
    it can cause damage, even if reports_dir and output_project are legitimate.
    """
    from quodeq.core.observability import NULL_LOG

    reports = tmp_path / "reports"
    proj = reports / "myproj"
    (proj / "run1").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.touch()

    result = _remove_run_directory(
        reports,
        output_project="myproj",
        run_uuid="../../../outside/sentinel",
        log=NULL_LOG,
    )

    assert result is False, "traversal run_uuid must not remove anything"
    assert sentinel.exists(), "traversal run_uuid must not reach rmtree"


def test_remove_run_directory_rejects_absolute_path_in_run_uuid(tmp_path: Path):
    """Absolute paths in run_uuid must not reach rmtree.

    An absolute-path-shaped run_uuid must be rejected before use.
    """
    from quodeq.core.observability import NULL_LOG

    reports = tmp_path / "reports"
    proj = reports / "myproj"
    (proj / "run1").mkdir(parents=True)
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()

    result = _remove_run_directory(
        reports,
        output_project="myproj",
        run_uuid=str(sentinel),
        log=NULL_LOG,
    )

    assert result is False, "absolute-path run_uuid must not remove anything"
    assert sentinel.exists(), "absolute-path run_uuid must not reach rmtree"


def test_remove_run_directory_allows_legitimate_paths(tmp_path: Path):
    """Normal legitimate project/run_uuid values work unchanged."""
    from quodeq.core.observability import NULL_LOG

    reports = tmp_path / "reports"
    run = reports / "myproj" / "run-123"
    run.mkdir(parents=True)
    (run / "status.json").write_text("{}")

    result = _remove_run_directory(
        reports,
        output_project="myproj",
        run_uuid="run-123",
        log=NULL_LOG,
    )

    assert result is True, "legitimate paths must be removed"
    assert not run.exists(), "legitimate paths must be deleted"


def test_remove_run_directory_scan_fallback_rejects_traversal(tmp_path: Path):
    """Fallback scan must also reject path traversal.

    When scanning without output_project, a traversal run_uuid must
    still be rejected before reaching rmtree.
    """
    from quodeq.core.observability import NULL_LOG

    reports = tmp_path / "reports"
    (reports / "proj1").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.mkdir()

    result = _remove_run_directory(
        reports,
        output_project=None,
        run_uuid="../../../outside/sentinel",
        log=NULL_LOG,
    )

    assert result is False, "fallback scan with traversal run_uuid must not remove anything"
    assert sentinel.exists(), "fallback scan traversal must not reach rmtree"
