from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.shared.run_status import RunState, write_status


def _seed_run(reports: Path, project: str, run_id: str, state: RunState) -> Path:
    d = reports / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, state=state, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    return d


def test_provider_list_evaluations_returns_indexed_rows(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rA", RunState.DONE)
    _seed_run(reports, "p", "rB", RunState.DONE)

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)
    job_ids = {j.job_id for j in jobs}
    assert {"ext-rA", "ext-rB"} <= job_ids
    assert all(j.status == "done" for j in jobs if j.job_id.startswith("ext-"))


def test_provider_get_evaluation_status_returns_row(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rX", RunState.RUNNING)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    snapshot = provider.get_evaluation_status("ext-rX", reports_dir=reports)
    assert snapshot is not None
    assert snapshot.job_id == "ext-rX"
    assert snapshot.status == "running"


def test_provider_list_repeated_call_works(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rA", RunState.DONE)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    provider.list_evaluations(limit=0, reports_dir=reports)
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)
    assert len(jobs) >= 1
    assert any(j.job_id == "ext-rA" for j in jobs)
