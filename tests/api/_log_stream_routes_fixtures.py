"""Shared fixtures and SSE parsing for tests/api/test_log_stream_routes*.py siblings."""
from __future__ import annotations

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

        def in_memory_job(self, job_id: str):
            return None  # no in-memory jobs: every run here is on disk

    provider = FakeProvider()
    app.config["_provider"] = provider
    register_log_stream_routes(app)
    return app


def _seed_run(tmp_path: Path, app: Flask, job_id: str, content: str) -> Path:
    run_dir = tmp_path / job_id
    run_dir.mkdir()
    # write_bytes preserves "\n" exactly. write_text on Windows would translate
    # "\n" to "\r\n", which then mismatches the byte offsets the route reports.
    (run_dir / "run.log").write_bytes(content.encode("utf-8"))
    app.config["_provider"].map[job_id] = run_dir
    return run_dir


def _collect_sse(resp, max_events: int = 50) -> list[dict]:
    """Parse an SSE response body into a list of {id, event, data} dicts."""
    events: list[dict] = []
    current: dict = {}
    for raw in resp.response:  # Flask test-client yields bytes chunks
        chunk = raw.decode("utf-8")
        for line in chunk.splitlines():
            if line.startswith("id:"):
                current["id"] = line[3:].strip()
            elif line.startswith("event:"):
                current["event"] = line[6:].strip()
            elif line.startswith("data:"):
                current["data"] = line[5:].strip()
            elif line == "":
                if current:
                    events.append(current)
                    current = {}
                    if len(events) >= max_events:
                        return events
    if current:
        events.append(current)
    return events
