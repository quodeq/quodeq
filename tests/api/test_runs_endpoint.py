from __future__ import annotations

import json

import pytest

from quodeq.api.app import create_app
from quodeq.services.run_index import open_index


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


def _seed_index(index_db_path):
    db = open_index(index_db_path)
    with db:
        db.execute(
            "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
            "started_at, updated_at, status_mtime) VALUES "
            "('ext-a','proj','a','/x/a','done','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',0)"
        )
    db.close()


def test_runs_endpoint_returns_unit(tmp_path, monkeypatch):
    evals = tmp_path / "evaluations"
    (evals / "proj").mkdir(parents=True)
    index_db = tmp_path / "index.db"
    _seed_index(index_db)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evals))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(index_db))
    import quodeq.services._runs_unit as ru
    monkeypatch.setattr(ru, "read_run_scalars", lambda *a, **k: [])

    app = create_app(static_dist=None, api_key=None)
    client = app.test_client()
    resp = client.get("/api/projects/proj/runs")
    assert resp.status_code == 200
    body = json.loads(resp.get_data())
    assert body["runs"][0]["runId"] == "a"
    assert body["runs"][0]["status"] == "complete"
    assert "ETag" in resp.headers


def test_runs_endpoint_304_on_matching_etag(tmp_path, monkeypatch):
    evals = tmp_path / "evaluations"
    (evals / "proj").mkdir(parents=True)
    index_db = tmp_path / "index.db"
    _seed_index(index_db)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evals))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(index_db))
    import quodeq.services._runs_unit as ru
    monkeypatch.setattr(ru, "read_run_scalars", lambda *a, **k: [])

    app = create_app(static_dist=None, api_key=None)
    client = app.test_client()
    first = client.get("/api/projects/proj/runs")
    etag = first.headers["ETag"]
    second = client.get("/api/projects/proj/runs", headers={"If-None-Match": etag})
    assert second.status_code == 304


def test_runs_endpoint_rejects_bad_project(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
    app = create_app(static_dist=None, api_key=None)
    client = app.test_client()
    resp = client.get("/api/projects/..%2f..%2fetc/runs")
    assert resp.status_code in (400, 404)


def test_runs_endpoint_400_on_invalid_segment(tmp_path, monkeypatch):
    # 'a..b' is a single routable path segment (no encoded slash), so it reaches
    # the handler and must fail validate_path_segment → 400 INVALID_INPUT.
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
    app = create_app(static_dist=None, api_key=None)
    client = app.test_client()
    resp = client.get("/api/projects/a..b/runs")
    assert resp.status_code == 400
    assert json.loads(resp.get_data())["code"] == "INVALID_INPUT"
