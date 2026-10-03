"""/scores ships the deferred payload; the detail route reads per kind."""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app


def _payload() -> dict:
    return {
        "accumulated": {"dimensions": [
            {"dimension": "security",
             "violations": [{"file": "a.py", "line": 1, "practiceId": "P1", "title": "t", "snippet": "s", "reason": "r", "context": "c", "reqRefs": []}],
             "compliance": [{"file": "b.py", "line": 2, "practiceId": "P1", "title": "ok", "snippet": "s", "reason": "r", "context": "c", "reqRefs": []}]},
        ], "summary": {}},
        "trend": [], "availableRuns": [], "scoring": {"customFormula": False},
    }


@pytest.fixture()
def served(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    state = {"calls": 0, "payload": _payload()}

    def fake_scores(root, project, as_of=None, *a, **kw):
        state["calls"] += 1
        return state["payload"]

    monkeypatch.setattr("quodeq.api._scores_routes.get_project_scores", fake_scores)
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c, state


def test_scores_defers_finding_detail(served):
    c, state = served
    a = c.get("/api/projects/p/scores").get_json()
    b = c.get("/api/projects/p/scores").get_json()
    assert a == b
    v = a["accumulated"]["dimensions"][0]["violations"][0]
    assert v["detailDeferred"] is True and "snippet" not in v and "reqRefs" not in v
    assert state["calls"] == 2


def test_deferring_does_not_mutate_the_service_payload(served):
    c, state = served
    c.get("/api/projects/p/scores")
    assert state["payload"]["accumulated"]["dimensions"][0]["violations"][0]["snippet"] == "s"


def test_detail_endpoint_serves_violations_and_compliance(served):
    c, _ = served
    v = c.get("/api/projects/p/compliance-detail?dimension=security&kind=violation").get_json()["items"]
    assert v[0]["snippet"] == "s" and v[0]["reqRefs"] == []
    comp = c.get("/api/projects/p/compliance-detail?dimension=security").get_json()["items"]
    assert comp[0]["file"] == "b.py" and comp[0]["reason"] == "r"
    assert c.get("/api/projects/p/compliance-detail?dimension=security&kind=other").status_code == 400
