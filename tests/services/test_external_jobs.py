"""Tests for filesystem-based external job detection."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# find_external_runs
# ---------------------------------------------------------------------------

def test_find_external_runs_identifies_in_progress(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    project = tmp_path / "proj-1"
    run = project / "run-A"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / "evaluation").mkdir()
    # No scan.json, but live .pid -> in-progress
    (run / ".pid").write_text(str(os.getpid()))

    results = find_external_runs(tmp_path)
    assert len(results) == 1
    snap = results[0]
    assert snap.status == "running"
    assert snap.source == "external"
    assert snap.job_id == "ext-run-A"
    assert snap.output_project == "proj-1"
    assert snap.output_run_id == "run-A"


def test_find_external_runs_skips_complete(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    run = tmp_path / "proj" / "done"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / "scan.json").write_text("{}")

    assert find_external_runs(tmp_path) == []


def test_find_external_runs_skips_run_without_manifest(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    run = tmp_path / "proj" / "no-manifest"
    (run / "evidence").mkdir(parents=True)
    # No manifest.json -> skip

    assert find_external_runs(tmp_path) == []


def test_find_external_runs_infers_phase_analyzing(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    run = tmp_path / "proj" / "active"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / "evidence" / "security_evidence.jsonl").write_text("")
    (run / "evaluation").mkdir()

    results = find_external_runs(tmp_path)
    assert len(results) == 1
    assert results[0].phase == "analyzing"
    assert results[0].current_dimension == "security"


def test_find_external_runs_scoring_phase_when_all_evidence_complete(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    run = tmp_path / "proj" / "active"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / "evidence" / "security_evidence.jsonl").write_text("")
    (run / "evaluation").mkdir()
    (run / "evaluation" / "security.json").write_text("{}")

    results = find_external_runs(tmp_path)
    # security completed, no in-progress evidence -> scoring
    assert len(results) == 1
    assert results[0].phase == "scoring"


def test_find_external_runs_setup_phase_when_no_evidence(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    run = tmp_path / "proj" / "active"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / "evaluation").mkdir()
    # No evidence files at all -> setup

    results = find_external_runs(tmp_path)
    assert len(results) == 1
    assert results[0].phase == "setup"


def test_find_external_runs_skips_dot_dirs(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    hidden = tmp_path / ".hidden" / "run"
    (hidden / "evidence").mkdir(parents=True)
    (hidden / "evidence" / "manifest.json").write_text("{}")

    assert find_external_runs(tmp_path) == []


def test_find_external_runs_empty_reports_root(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    assert find_external_runs(tmp_path) == []


def test_find_external_runs_nonexistent_reports_root(tmp_path):
    from quodeq.services._external_jobs import find_external_runs

    assert find_external_runs(tmp_path / "does-not-exist") == []


# ---------------------------------------------------------------------------
# PID resolution
# ---------------------------------------------------------------------------

def test_resolve_external_pid_returns_none_without_pid_file(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    (tmp_path / "proj" / "run").mkdir(parents=True)
    assert resolve_external_pid("proj", "run", tmp_path) is None


def test_resolve_external_pid_returns_pid_when_alive(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text(str(os.getpid()))
    assert resolve_external_pid("proj", "run", tmp_path) == os.getpid()


def test_resolve_external_pid_returns_none_when_process_dead(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    # Use a very high PID that's almost certainly not in use
    (run_dir / ".pid").write_text("999999")
    assert resolve_external_pid("proj", "run", tmp_path) is None


def test_resolve_external_pid_returns_none_for_corrupt_pid_file(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text("not-a-number")
    assert resolve_external_pid("proj", "run", tmp_path) is None


# ---------------------------------------------------------------------------
# cancel_external_run
# ---------------------------------------------------------------------------

def test_cancel_external_run_returns_false_without_pid_file(tmp_path):
    from quodeq.services._external_jobs import cancel_external_run

    (tmp_path / "proj" / "run").mkdir(parents=True)
    assert cancel_external_run("proj", "run", tmp_path) is False


# ---------------------------------------------------------------------------
# JobManager list_jobs merge/dedup
# ---------------------------------------------------------------------------

def _make_in_progress_run(reports_root: Path, project: str, run_id: str) -> None:
    """Create an in-progress run directory structure."""
    run_dir = reports_root / project / run_id
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "evaluation").mkdir()
    # No scan.json => in-progress


def test_list_jobs_merges_external_runs(tmp_path):
    from quodeq.services.jobs import JobManager

    _make_in_progress_run(tmp_path, "proj-ext", "run-ext-1")

    jm = JobManager()
    jobs = jm.list_jobs(reports_root=tmp_path)

    assert any(j.job_id == "ext-run-ext-1" for j in jobs)
    assert any(j.source == "external" for j in jobs)


def test_list_jobs_deduplicates_by_output_project_run_id(tmp_path):
    """An internal job tracking the same run must suppress the external snapshot."""
    from quodeq.services.jobs import JobManager
    from quodeq.services._job_model import Job
    from collections import deque

    _make_in_progress_run(tmp_path, "proj-shared", "run-shared")

    jm = JobManager()
    # Register an internal job that claims the same (project, run_id)
    internal = Job(
        job_id="internal-abc",
        status="running",
        command=[],
        started_at="2026-01-01T00:00:00+00:00",
        ended_at=None,
        exit_code=None,
        output_project="proj-shared",
        output_run_id="run-shared",
    )
    jm._store.put(internal)

    jobs = jm.list_jobs(reports_root=tmp_path)
    job_ids = [j.job_id for j in jobs]
    # Internal wins; external must be absent
    assert "internal-abc" in job_ids
    assert "ext-run-shared" not in job_ids


def test_list_jobs_without_reports_root_only_returns_internal(tmp_path):
    from quodeq.services.jobs import JobManager

    _make_in_progress_run(tmp_path, "proj-ext", "run-ext-2")

    jm = JobManager()
    jobs = jm.list_jobs()  # no reports_root
    assert not any(j.source == "external" for j in jobs)


def test_get_job_handles_ext_prefix(tmp_path):
    from quodeq.services.jobs import JobManager

    _make_in_progress_run(tmp_path, "proj-ext", "run-ext-3")

    jm = JobManager()
    snap = jm.get_job("ext-run-ext-3", reports_root=tmp_path)
    assert snap is not None
    assert snap.job_id == "ext-run-ext-3"
    assert snap.source == "external"


def test_get_job_ext_prefix_returns_none_when_not_found(tmp_path):
    from quodeq.services.jobs import JobManager

    jm = JobManager()
    assert jm.get_job("ext-nonexistent", reports_root=tmp_path) is None


def test_get_job_ext_prefix_requires_reports_root():
    from quodeq.services.jobs import JobManager

    jm = JobManager()
    # Without reports_root, falls through to internal store -> None
    assert jm.get_job("ext-anything") is None


# ---------------------------------------------------------------------------
# PID liveness — find_external_runs status
# ---------------------------------------------------------------------------

def _seed_in_progress_run(
    tmp_path: Path,
    project: str = "p",
    run_id: str = "r",
    pid_content: str | None = None,
) -> Path:
    """Create a run_dir with manifest.json (no scan.json). Optionally write a .pid file."""
    run_dir = tmp_path / project / run_id
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "evaluation").mkdir()
    if pid_content is not None:
        (run_dir / ".pid").write_text(pid_content)
    return run_dir


def test_live_pid_is_reported_as_running(tmp_path: Path) -> None:
    """Run with .pid pointing at a live process -> status='running'."""
    from quodeq.services._external_jobs import find_external_runs

    _seed_in_progress_run(tmp_path, pid_content=str(os.getpid()))
    runs = find_external_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].status == "running"


def test_dead_pid_is_reported_as_cancelled(tmp_path: Path) -> None:
    """Run with .pid pointing at a dead process -> status='cancelled' (stale)."""
    from quodeq.services._external_jobs import find_external_runs

    # A PID of 999999999 is virtually guaranteed to be absent on modern systems.
    _seed_in_progress_run(tmp_path, pid_content="999999999")
    runs = find_external_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].status == "cancelled"


def test_missing_pid_defaults_to_cancelled(tmp_path: Path) -> None:
    """Run with manifest but no .pid file -> treat as stale (status='cancelled').

    A healthy run writes .pid early and unlinks it in the finally block only
    *after* scan.json is written. If scan.json is absent AND .pid is absent,
    the process died before writing .pid OR finished abnormally -- in either
    case we have no evidence of liveness and should not block the UI.
    """
    from quodeq.services._external_jobs import find_external_runs

    _seed_in_progress_run(tmp_path, pid_content=None)
    runs = find_external_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].status == "cancelled"


def test_malformed_pid_is_reported_as_cancelled(tmp_path: Path) -> None:
    """Run with a non-numeric .pid file -> status='cancelled' (treat as stale)."""
    from quodeq.services._external_jobs import find_external_runs

    _seed_in_progress_run(tmp_path, pid_content="not-a-pid")
    runs = find_external_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].status == "cancelled"
