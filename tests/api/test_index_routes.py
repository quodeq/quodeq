from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest

from quodeq.shared.run_status import RunState, write_status


def _seed_run(reports: Path, project: str, run_id: str) -> Path:
    d = reports / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, state=RunState.DONE, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    return d


def test_rebuild_endpoint_registered(monkeypatch, tmp_path) -> None:
    from quodeq.api.app import create_app
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/index/rebuild" in rules


def test_rebuild_returns_count_and_elapsed(monkeypatch, tmp_path) -> None:
    from quodeq.api.app import create_app
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rA")
    _seed_run(reports, "p", "rB")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))

    app = create_app()
    client = app.test_client()
    resp = client.post("/api/index/rebuild", headers={"Origin": "http://localhost"})
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data["count"] == 2
    assert data["elapsed_ms"] >= 0
