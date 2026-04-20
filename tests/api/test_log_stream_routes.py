from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest
from flask import Flask

from quodeq.api._log_stream_routes import register_log_stream_routes


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    app = Flask(__name__)
    app.config["_api_key"] = None  # localhost-only mode, works with test client
    app.config["_reports_dir"] = tmp_path

    # Fake provider that resolves job_id -> run_dir via run_dir mapping.
    class FakeProvider:
        def __init__(self) -> None:
            self.map: dict[str, Path] = {}

        def get_log_run_dir(self, job_id: str) -> Path | None:
            return self.map.get(job_id)

        def is_job_complete(self, job_id: str) -> bool:
            return job_id.endswith("-done")

    provider = FakeProvider()
    app.config["_provider"] = provider
    register_log_stream_routes(app)
    return app


def _seed_run(tmp_path: Path, app: Flask, job_id: str, content: str) -> Path:
    run_dir = tmp_path / job_id
    run_dir.mkdir()
    (run_dir / "run.log").write_text(content)
    app.config["_provider"].map[job_id] = run_dir
    return run_dir


def test_plain_logs_returns_content(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-1-done", "first\nsecond\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-1-done/logs")
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data["lines"] == ["first", "second"]
    assert data["nextOffset"] == len("first\nsecond\n")
    assert data["done"] is True


def test_plain_logs_since_offset(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-2", "first\nsecond\nthird\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-2/logs?since=6")  # after "first\n"
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data["lines"] == ["second", "third"]


def test_plain_logs_404_when_log_missing(tmp_path, app) -> None:
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    app.config["_provider"].map["job-3"] = run_dir
    client = app.test_client()
    resp = client.get("/api/jobs/job-3/logs")
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_plain_logs_410_when_run_dir_missing(tmp_path, app) -> None:
    app.config["_provider"].map["job-4"] = tmp_path / "gone"  # not a real dir
    client = app.test_client()
    resp = client.get("/api/jobs/job-4/logs")
    assert resp.status_code == HTTPStatus.GONE


def test_plain_logs_partial_line_stripped(tmp_path, app) -> None:
    """If the last line lacks a trailing newline, it's not returned — caller polls again."""
    _seed_run(tmp_path, app, "job-5", "complete\npartial-tail")
    client = app.test_client()
    resp = client.get("/api/jobs/job-5/logs")
    data = resp.get_json()
    assert data["lines"] == ["complete"]
    assert data["nextOffset"] == len("complete\n")
