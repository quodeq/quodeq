"""End-to-end: real CLI runs are visible in the DB-backed /api/evaluations response."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_cli_run_appears_in_index(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def f(): return 1\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    env = {
        **os.environ,
        "QUODEQ_EVALUATIONS_DIR": str(reports),
        "QUODEQ_INDEX_DB_PATH": str(tmp_path / "idx.db"),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "quodeq.cli", "evaluate", str(src), "--dry-run", "-d", "security",
         "-o", str(reports)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}"

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    from quodeq.api.app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/evaluations")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    assert len(data) >= 1
    ext_jobs = [j for j in data if j.get("jobId", "").startswith("ext-")]
    assert ext_jobs, f"no ext- job returned; got {data}"
    states = {j["status"] for j in ext_jobs}
    assert "done" in states, f"expected 'done', got {states}"


@pytest.mark.integration
def test_legacy_run_appears_as_cancelled(tmp_path: Path, monkeypatch) -> None:
    """A pre-Plan-A run dir (no status.json, no .pid) shows up as cancelled."""
    reports = tmp_path / "reports"
    run = reports / "p" / "legacy-run"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    from quodeq.api.app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/evaluations")
    data = resp.get_json()
    legacy = [j for j in (data or []) if j.get("jobId") == "ext-legacy-run"]
    assert len(legacy) == 1
    assert legacy[0]["status"] == "cancelled"
