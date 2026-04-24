# tests/api/test_log_stream_real_provider.py
"""End-to-end: real FilesystemActionProvider must resolve run_dir for log streaming."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest

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
