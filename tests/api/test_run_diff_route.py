"""GET /api/projects/<project>/runs/<run_id>/diff serves the run-diff payload."""
from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

import pytest

from quodeq.api.app import create_app

_PROJECT = "proj"
_PREV = "run-prev"
_CURR = "run-curr"
_DIM = "maintainability"


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


def _report(run_dir: Path, violations: list[dict], started_at: str) -> None:
    (run_dir / "evaluation").mkdir(parents=True, exist_ok=True)
    (run_dir / "evaluation" / f"{_DIM}.json").write_text(json.dumps({
        "dimension": _DIM, "principles": [], "violations": violations, "compliance": [],
    }), encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps({
        "state": "done", "started_at": started_at}), encoding="utf-8")


@pytest.fixture
def client(tmp_path, monkeypatch):
    evals = tmp_path / "evaluations"
    _report(evals / _PROJECT / _PREV,
            [{"req": "M-REU-1", "file": "b.py", "line": 2, "snippet": "dup()", "severity": "minor"}],
            "2026-09-20T00:00:00Z")
    _report(evals / _PROJECT / _CURR,
            [{"req": "M-ANA-9", "file": "a.py", "line": 5, "snippet": "long", "severity": "minor"}],
            "2026-09-26T00:00:00Z")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evals))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    app = create_app(static_dist=None, api_key=None)
    return app.test_client()


def test_run_diff_route_returns_payload(client) -> None:
    resp = client.get(f"/api/projects/{_PROJECT}/runs/{_CURR}/diff?against={_PREV}")
    assert resp.status_code == HTTPStatus.OK
    body = resp.get_json()
    assert (body["runId"], body["againstRunId"]) == (_CURR, _PREV)
    assert body["dimensions"][_DIM]["counts"]["new"] == 1
    assert body["dimensions"][_DIM]["types"]["closed"] == ["M-REU-1"]


def test_run_diff_route_unknown_run_is_404(client) -> None:
    resp = client.get(f"/api/projects/{_PROJECT}/runs/nope/diff")
    assert resp.status_code == HTTPStatus.NOT_FOUND
    assert resp.get_json()["code"] == "NOT_FOUND"


def test_run_diff_route_rejects_bad_segment(client) -> None:
    resp = client.get(f"/api/projects/{_PROJECT}/runs/{_CURR}/diff?against=..")
    assert resp.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND)
