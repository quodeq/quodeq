"""Cluster 32: services best-effort handlers log through the injected LogSink."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from quodeq.services import (
    _evaluations_index,
    _fs_reports,
    _repo_index,
    _run_discard,
    _score_cache_fetch,
    jobs,
    project_registration,
    shared_settings,
    violations,
)
from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._job_model import InMemoryJobStore
from quodeq.services.shared_settings import SharedSettings


def test_enrich_with_coverage_logs_corrupt_scan_json(tmp_path, recording_log) -> None:
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / _fs_reports._SCAN_FILENAME).write_text("{not json", encoding="utf-8")
    payload = {"filesCount": 3}
    out = _fs_reports._enrich_with_coverage(str(tmp_path), "proj", payload, log=recording_log)
    assert out is payload
    assert "totalFiles" not in out
    assert recording_log.debug_messages
    assert "coverage enrichment skipped" in recording_log.debug_messages[0]


def test_get_dashboard_threads_log_into_enrichment(tmp_path, recording_log, monkeypatch) -> None:
    monkeypatch.setattr(_fs_reports, "build_dashboard", lambda *_a, **_k: {"filesCount": 1})
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / _fs_reports._SCAN_FILENAME).write_text("[", encoding="utf-8")
    _fs_reports.get_dashboard(str(tmp_path), "proj", "run-1", log=recording_log)
    assert recording_log.debug_messages


def test_wait_for_terminal_status_logs_once_while_status_is_missing(tmp_path, recording_log) -> None:
    ok = _run_discard._wait_for_terminal_status(
        tmp_path, timeout_s=0.05, poll_interval_s=0.01, log=recording_log,
    )
    assert ok is False
    assert len(recording_log.debug_messages) == 1
    assert "status.json" in recording_log.debug_messages[0]


def test_write_settings_logs_when_quodeq_dir_is_a_file(tmp_path, recording_log) -> None:
    blocker = tmp_path / "quodeq-dir"
    blocker.write_text("", encoding="utf-8")  # mkdir(parents=True, exist_ok=True) on a file raises FileExistsError
    shared_settings.write_settings(
        SharedSettings(url="https://example.test"), env={"QUODEQ_DIR": str(blocker)}, log=recording_log,
    )
    assert recording_log.debug_messages
    assert "shared settings write failed" in recording_log.debug_messages[0]


def test_rollback_new_dirs_warns_when_rmtree_fails(tmp_path, recording_log, monkeypatch) -> None:
    (tmp_path / "new-project").mkdir()

    def _denied(path, *_a, **_k):
        raise OSError(13, "Permission denied", str(path))

    monkeypatch.setattr(project_registration.shutil, "rmtree", _denied)
    project_registration._rollback_new_dirs(str(tmp_path), before=set(), log=recording_log)
    assert recording_log.warning_messages
    assert "rollback could not remove" in recording_log.warning_messages[0]
    assert (tmp_path / "new-project").exists()


def test_rollback_and_report_runs_the_callable() -> None:
    calls: list[str] = []
    result = project_registration._rollback_and_report(lambda: calls.append("rolled back"), "invalid_repo", "bad url")
    assert calls == ["rolled back"]
    assert result.status == "invalid_repo"
    assert result.message == "bad url"


def test_cached_accumulated_logs_recheck_read_failure(monkeypatch, recording_log) -> None:
    reads = {"n": 0}

    def _read(_conn, _project, _version):
        reads["n"] += 1
        if reads["n"] == 1:
            return None  # first look: miss, so we enter the single-flight block
        raise sqlite3.Error("locked")  # re-check inside single-flight: fails

    @contextmanager
    def _fake_cache():
        yield object()

    monkeypatch.setattr(_score_cache_fetch, "read_cached_accumulated", _read)
    monkeypatch.setattr(_score_cache_fetch, "open_score_cache", _fake_cache)
    monkeypatch.setattr(_score_cache_fetch, "write_cached_accumulated", lambda *_a, **_k: None)
    # signature: cached_accumulated(project, version, compute, cacheable=None, *, log=NULL_LOG)
    result = _score_cache_fetch.cached_accumulated(
        project="p", version="v1", compute=lambda: {"score": 1}, log=recording_log,
    )
    assert result == {"score": 1}
    assert recording_log.debug_messages
    assert "re-check read failed" in recording_log.debug_messages[0]


def test_cached_project_summary_logs_recheck_read_failure(monkeypatch, recording_log) -> None:
    reads = {"n": 0}

    def _read(_conn, _project, _version):
        reads["n"] += 1
        if reads["n"] == 1:
            return None  # first look: miss, so we enter the single-flight block
        raise sqlite3.Error("locked")  # re-check inside single-flight: fails

    @contextmanager
    def _fake_cache():
        yield object()

    monkeypatch.setattr(_score_cache_fetch, "read_cached_project_summary", _read)
    monkeypatch.setattr(_score_cache_fetch, "open_score_cache", _fake_cache)
    monkeypatch.setattr(_score_cache_fetch, "write_cached_project_summary", lambda *_a, **_k: None)
    result = _score_cache_fetch.cached_project_summary(
        project="p", version="v1", compute=lambda: {"score": 1}, log=recording_log,
    )
    assert result == {"score": 1}
    assert recording_log.debug_messages
    assert "re-check read failed" in recording_log.debug_messages[0]


def test_evaluations_index_delete_logs_when_job_manager_entry_already_gone(tmp_path, monkeypatch) -> None:
    reports_root = tmp_path / "reports"
    reports_root.mkdir()

    class _RaisingJobs:
        """Stands in for a JobManager whose in-memory entry is already gone."""

        def delete(self, job_id: str) -> bool:
            raise KeyError(job_id)

    index = EvaluationsIndex(
        jobs=_RaisingJobs(), index_db_path=tmp_path / "index.db", reports_root=reports_root,
    )
    snapshot = _evaluations_index.JobSnapshot(
        job_id="job-1", status="done", output_project="proj", output_run_id="run-1",
    )
    monkeypatch.setattr(index, "get_status", lambda *_a, **_k: snapshot)

    with patch.object(_evaluations_index._logger, "debug") as mock_debug:
        result = index.delete("job-1", reports_dir=reports_root)

    assert result is False  # run dir never existed on disk
    mock_debug.assert_called_once()
    assert "in-memory job entry already gone on delete" in mock_debug.call_args[0][0]


def test_save_repo_index_logs_when_tmp_cleanup_also_fails(tmp_path, recording_log, monkeypatch) -> None:
    def _raise_replace(*_a, **_k):
        raise OSError("target locked")

    def _raise_unlink(*_a, **_k):
        raise OSError("cannot remove tmp")

    monkeypatch.setattr(_repo_index.os, "replace", _raise_replace)
    monkeypatch.setattr(_repo_index.os, "unlink", _raise_unlink)

    _repo_index._save_repo_index(tmp_path, {"a": "b"}, log=recording_log)

    assert recording_log.warning_messages  # the pre-existing outer failure log
    assert recording_log.debug_messages  # the new inner cleanup-failure log
    assert "temp repo index file not removed after a failed save" in recording_log.debug_messages[0]


def test_job_manager_shutdown_logs_when_kill_tree_fails(recording_log, monkeypatch) -> None:
    manager = jobs.JobManager(job_store=InMemoryJobStore(), log=recording_log)
    manager._processes["job-1"] = SimpleNamespace(pid=99999)

    def _raiser(pid):
        raise ProcessLookupError(pid)

    monkeypatch.setattr(jobs, "_kill_tree", _raiser)
    manager.shutdown()

    assert recording_log.debug_messages
    assert "job job-1 process already gone during shutdown" in recording_log.debug_messages[0]
    assert manager._processes == {}


def test_dismissed_key_for_violation_logs_unparsable_line(monkeypatch) -> None:
    with patch.object(violations._logger, "debug") as mock_debug:
        key = violations._dismissed_key_for_violation({"req": "REQ-1", "file": "main.py:not-a-number"})
    assert key == ("REQ-1", "main.py:not-a-number", 0)
    mock_debug.assert_called_once()
    assert "violation line could not be parsed" in mock_debug.call_args[0][0]
