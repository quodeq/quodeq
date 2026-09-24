"""/scores defers compliance detail; /compliance-detail serves it on demand.

Compliance context, snippet and reason were ~75% of a 28MB /scores payload on
a real project, and only the Principle and File detail pages render them.
"""
from __future__ import annotations

import copy

import pytest

from quodeq.api.app import create_app


def _item(file: str, line: int, principle: str, **extra) -> dict:
    return {
        "file": file, "line": line, "practiceId": principle, "title": f"{principle} ok",
        "context": f"ctx {file}:{line}", "snippet": f"code {file}:{line}", "reason": "why",
        **extra,
    }


def _payload() -> dict:
    return {
        "accumulated": {
            "dimensions": [
                {
                    "dimension": "security",
                    "violations": [{"file": "a.py", "line": 1, "snippet": "kept", "reason": "kept"}],
                    "compliance": [
                        _item("src/a.py", 1, "P1"),
                        _item("src/b.py", 2, "P2"),
                        _item("lib/c.py", 3, "P1"),
                    ],
                },
                {"dimension": "usability", "violations": [], "compliance": [_item("src/a.py", 9, "U1")]},
            ],
            "summary": {},
        },
        "trend": [],
        "availableRuns": [],
        "scoring": {"customFormula": False},
    }


@pytest.fixture()
def served(tmp_path, monkeypatch):
    """A client whose get_project_scores returns one shared payload object,
    the way the accumulated cache hands out the same dict on every hit."""
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    payload = _payload()
    calls: list[tuple] = []

    def fake_scores(root, project, as_of=None, *a, **kw):
        calls.append((project, as_of))
        return payload

    monkeypatch.setattr("quodeq.api._scores_routes.get_project_scores", fake_scores)
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c, payload, calls


def test_scores_drops_compliance_detail_and_marks_it_deferred(served) -> None:
    client, _, _ = served
    body = client.get("/api/projects/demo/scores").get_json()

    item = body["accumulated"]["dimensions"][0]["compliance"][0]
    assert "context" not in item and "snippet" not in item and "reason" not in item
    assert item["detailDeferred"] is True
    assert (item["file"], item["line"], item["practiceId"], item["title"]) == ("src/a.py", 1, "P1", "P1 ok")


def test_scores_keeps_violation_detail(served) -> None:
    client, _, _ = served
    body = client.get("/api/projects/demo/scores").get_json()

    violation = body["accumulated"]["dimensions"][0]["violations"][0]
    assert violation["snippet"] == "kept" and violation["reason"] == "kept"


def test_scores_does_not_mutate_the_cached_payload(served) -> None:
    client, payload, _ = served
    before = copy.deepcopy(payload)

    client.get("/api/projects/demo/scores")

    assert payload == before


def test_detail_returns_full_items_for_one_dimension(served) -> None:
    client, _, _ = served
    body = client.get("/api/projects/demo/compliance-detail?dimension=security").get_json()

    assert [i["file"] for i in body["items"]] == ["src/a.py", "src/b.py", "lib/c.py"]
    assert body["items"][0]["snippet"] == "code src/a.py:1"
    assert "detailDeferred" not in body["items"][0]


def test_detail_filters_by_principle(served) -> None:
    client, _, _ = served
    body = client.get("/api/projects/demo/compliance-detail?dimension=security&principle=P1").get_json()

    assert [(i["file"], i["line"]) for i in body["items"]] == [("src/a.py", 1), ("lib/c.py", 3)]


def test_detail_filters_by_path_prefix(served) -> None:
    client, _, _ = served
    body = client.get("/api/projects/demo/compliance-detail?dimension=security&pathPrefix=src/").get_json()

    assert [i["file"] for i in body["items"]] == ["src/a.py", "src/b.py"]


def test_detail_passes_as_of_through(served) -> None:
    client, _, calls = served
    client.get("/api/projects/demo/compliance-detail?dimension=security&asOf=run-7")

    assert calls[-1] == ("demo", "run-7")


def test_detail_unknown_dimension_is_empty(served) -> None:
    client, _, _ = served
    body = client.get("/api/projects/demo/compliance-detail?dimension=nope").get_json()

    assert body["items"] == []


def test_detail_requires_a_dimension(served) -> None:
    client, _, _ = served
    resp = client.get("/api/projects/demo/compliance-detail")

    assert resp.status_code == 400


def test_detail_rejects_traversal_project(served) -> None:
    client, _, _ = served
    resp = client.get("/api/projects/..%2Fetc/compliance-detail?dimension=security")

    assert resp.status_code in (400, 404)


def test_detail_missing_project_is_404(served, monkeypatch) -> None:
    client, _, _ = served
    monkeypatch.setattr("quodeq.api._scores_routes.get_project_scores", lambda *a, **kw: None)
    resp = client.get("/api/projects/demo/compliance-detail?dimension=security")

    assert resp.status_code == 404
