"""POST /api/findings/dismiss-by-type closes a requirement in one request."""
from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

import pytest
from flask import Flask

from quodeq.api.routes_findings_by_type import register_findings_by_type_routes
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository

_PROJECT = "proj"
_RUN = "run-1"
_DIM = "security"
_ROUTE = "/api/findings/dismiss-by-type"


def _seed(evals: Path) -> None:
    """A run with both the event log (rescore) and the report (what the UI counts)."""
    run_dir = evals / _PROJECT / _RUN
    (run_dir / "evaluation").mkdir(parents=True)
    writer = EventLogWriter(run_dir / "events.jsonl")
    reqs = ["S-1", "S-1", "S-2"]
    for i, req in enumerate(reqs):
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="Integrity", verdict="violation", dimension=_DIM, file=f"f{i}.py",
            line=10 + i, reason="r", req=req, severity="critical", snippet=f"c{i}")))
    SqliteFindingsRepository(run_dir).list_by_dimension(_DIM)
    (run_dir / "evaluation" / f"{_DIM}.json").write_text(json.dumps({
        "dimension": _DIM, "principles": [], "compliance": [],
        "violations": [{"principle": "Integrity", "file": f"f{i}.py", "line": 10 + i, "req": req,
                        "severity": "critical", "snippet": f"c{i}", "reason": "r"} for i, req in enumerate(reqs)],
    }), encoding="utf-8")


@pytest.fixture
def client(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_findings_by_type_routes(app)
    _seed(tmp_path)
    return app.test_client()


def test_dismiss_by_type_returns_count_scores_and_delta(client) -> None:
    resp = client.post(_ROUTE, json={"project": _PROJECT, "req": "S-1", "dimension": _DIM, "run_id": _RUN})
    assert resp.status_code == HTTPStatus.OK
    body = resp.get_json()
    assert (body["ok"], body["dismissed"]) == (True, 2)
    assert body["delta"]["kind"] == "dismiss_many"
    assert (body["delta"]["req"], body["delta"]["count"]) == ("S-1", 2)
    assert "scores" in body


def test_dismiss_by_type_requires_the_scope(client) -> None:
    resp = client.post(_ROUTE, json={"project": _PROJECT, "req": "S-1"})
    assert (resp.status_code, resp.get_json()["code"]) == (HTTPStatus.BAD_REQUEST, "MISSING_PARAM")


def test_dismiss_by_type_rejects_wrong_types(client) -> None:
    resp = client.post(_ROUTE, json={"project": _PROJECT, "req": "S-1", "dimension": _DIM, "run_id": _RUN, "principle": 3})
    assert (resp.status_code, resp.get_json()["code"]) == (HTTPStatus.BAD_REQUEST, "INVALID_PARAM")


def test_dismiss_by_type_unknown_run_is_404(client) -> None:
    resp = client.post(_ROUTE, json={"project": _PROJECT, "req": "S-1", "dimension": _DIM, "run_id": "nope"})
    assert (resp.status_code, resp.get_json()["code"]) == (HTTPStatus.NOT_FOUND, "NOT_FOUND")
