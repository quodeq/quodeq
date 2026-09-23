# tests/api/test_log_stream_real_provider.py
"""End-to-end: real FilesystemActionProvider must resolve run_dir for log streaming."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path


from quodeq.api.app import create_app


def test_get_log_run_dir_resolves_external_run_with_real_provider(tmp_path: Path, monkeypatch) -> None:
    """After setting QUODEQ_EVALUATIONS_DIR, the default provider resolves ext-<run_id> to the right run_dir."""
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))

    # Seed a fake in-progress run.
    project = tmp_path / "proj-x"
    run = project / "run-abc"
    run.mkdir(parents=True)
    (run / "evidence").mkdir()
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / "run.log").write_text("hello\nworld\n")

    app = create_app()
    client = app.test_client()

    # Plain endpoint must find the log file and return its contents.
    resp = client.get("/api/jobs/ext-run-abc/logs")
    assert resp.status_code == HTTPStatus.OK, (
        f"real-provider log resolution broken: {resp.status_code} {resp.get_json()}"
    )
    data = resp.get_json()
    assert data["lines"] == ["hello", "world"]


class _StubJobs:
    """In-memory JobManager stand-in: one internal job with a fixed snapshot."""

    def __init__(self, snapshot) -> None:
        self._snapshot = snapshot

    def get_job(self, job_id):
        return self._snapshot if job_id == self._snapshot.job_id else None

    def __getattr__(self, name):
        raise AttributeError(name)


def _real_provider_app(tmp_path: Path, snapshot):
    from quodeq.services.filesystem import FilesystemActionProvider

    provider = FilesystemActionProvider(
        job_manager=_StubJobs(snapshot),
        index_db_path=tmp_path / "index.db",
        reports_root=tmp_path / "reports",
    )
    return create_app(provider=provider).test_client()


def test_stream_stays_open_for_a_preparing_internal_job_with_real_provider(tmp_path: Path) -> None:
    """Right after Start the job has no report_path marker yet: the stream must open, not 404."""
    from quodeq.core.types.job import JobSnapshot

    snapshot = JobSnapshot(job_id="job-1", status="running", output_project=None)
    client = _real_provider_app(tmp_path, snapshot)

    resp = client.get("/api/jobs/job-1/logs/stream", buffered=False)
    try:
        assert resp.status_code == HTTPStatus.OK
    finally:
        resp.close()


def test_stream_done_frame_uses_the_in_memory_status_with_real_provider(tmp_path: Path) -> None:
    """The in-memory status beats a status.json the runner has not flushed yet."""
    import json

    from quodeq.core.types.job import JobSnapshot

    run_dir = tmp_path / "reports" / "proj" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.log").write_text("hello\n", encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")
    snapshot = JobSnapshot(
        job_id="job-1", status="cancelled", output_project="proj", output_run_id="run-1",
    )
    client = _real_provider_app(tmp_path, snapshot)

    body = client.get("/api/jobs/job-1/logs/stream").get_data(as_text=True)

    assert "event: done\ndata: cancelled" in body
