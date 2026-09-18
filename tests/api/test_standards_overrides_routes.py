"""Tests for GET/PUT /api/projects/<project_id>/standards-overrides: round-trips, validation and malformed specs."""
import json
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from tests.api._standards_overrides_fixtures import (  # noqa: F401 -- pytest fixtures
    _LOCALHOST,
    OVERRIDES_URL,
    client,
    client_with_custom,
    client_without_repo_root,
    project_root,
)


def test_get_returns_empty_when_no_file(client):
    resp = client.get(OVERRIDES_URL)
    assert resp.status_code == 200
    assert resp.get_json() == {"overrides": {}, "counts": {}}


def test_put_then_get_roundtrip(client, project_root: Path):
    resp = client.put(OVERRIDES_URL, json={"overrides": {"M-ANA-2": {"max_lines": 60}}},
                      headers=_LOCALHOST)
    assert resp.status_code == 200
    saved = json.loads((project_root / ".quodeq" / "standards-overrides.json").read_text())
    assert saved == {"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}
    resp = client.get(OVERRIDES_URL)
    assert resp.get_json() == {
        "overrides": {"M-ANA-2": {"max_lines": 60}},
        "counts": {"maintainability": 1},
    }


def test_put_rejects_out_of_bounds(client, project_root: Path):
    resp = client.put(OVERRIDES_URL, json={"overrides": {"M-ANA-2": {"max_lines": 99999}}},
                      headers=_LOCALHOST)
    assert resp.status_code == 400
    body = resp.get_json()
    assert "details" in body
    assert any("M-ANA-2.max_lines" in d for d in body["details"])
    assert not (project_root / ".quodeq" / "standards-overrides.json").exists()


def test_put_empty_deletes_file(client, project_root: Path):
    client.put(OVERRIDES_URL, json={"overrides": {"M-ANA-2": {"max_lines": 60}}},
               headers=_LOCALHOST)
    resp = client.put(OVERRIDES_URL, json={"overrides": {}}, headers=_LOCALHOST)
    assert resp.status_code == 200
    assert not (project_root / ".quodeq" / "standards-overrides.json").exists()


def test_unknown_project_is_404(client_without_repo_root):
    resp = client_without_repo_root.get(OVERRIDES_URL)
    assert resp.status_code == 404


def test_put_accepts_override_for_evaluator_only_requirement(client_with_custom, project_root: Path):
    """PUT must not 400 for a req declared only in the evaluators dir."""
    resp = client_with_custom.put(
        OVERRIDES_URL,
        json={"overrides": {"CUST-1": {"max_items": 50}}},
        headers=_LOCALHOST,
    )
    assert resp.status_code == 200
    saved = json.loads((project_root / ".quodeq" / "standards-overrides.json").read_text())
    assert saved["overrides"]["CUST-1"] == {"max_items": 50}


def test_put_accepts_override_for_compiled_req_alongside_evaluator(client_with_custom, project_root: Path):
    """PUT accepts overrides for both compiled and evaluator requirements at once."""
    resp = client_with_custom.put(
        OVERRIDES_URL,
        json={"overrides": {
            "M-ANA-2": {"max_lines": 60},
            "CUST-1": {"max_items": 200},
        }},
        headers=_LOCALHOST,
    )
    assert resp.status_code == 200
    saved = json.loads((project_root / ".quodeq" / "standards-overrides.json").read_text())
    assert saved["overrides"]["M-ANA-2"] == {"max_lines": 60}
    assert saved["overrides"]["CUST-1"] == {"max_items": 200}


# ---------------------------------------------------------------------------
# Fix 3: validate_overrides — missing bounds yields clean error, not 500
# ---------------------------------------------------------------------------

def test_put_malformed_spec_missing_bounds_does_not_500(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A user-authored evaluator spec without min/max must yield a clean validation
    error (or accept unbounded integers), never raise a KeyError / 500."""
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()

    # Evaluator spec with no min/max — user-authored edge case
    (evaluators / "loose.json").write_text(json.dumps({
        "id": "loose",
        "type": "custom",
        "managed": False,
        "principles": [{"name": "P", "requirements": [{
            "id": "LOOSE-1",
            "text": "At most {threshold} things",
            "params": {"threshold": {"label": "Threshold", "type": "int", "default": 10}},
        }]}],
    }))

    project_root = tmp_path / "repo"
    project_root.mkdir()

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: str(project_root))

    with app.test_client() as c:
        # A value within "unbounded" range should be accepted (mirrors _is_valid)
        resp = c.put(
            OVERRIDES_URL,
            json={"overrides": {"LOOSE-1": {"threshold": 42}}},
            headers=_LOCALHOST,
        )
        assert resp.status_code in (200, 400)  # must NOT be 500
        assert resp.status_code != 500


def test_put_shape_invalid_param_spec_does_not_500(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A compiled dimension file whose params spec is a bare value (not a
    dict) must not crash _changed_dimensions with AttributeError. Same
    degrade-and-skip contract as an unreadable/unparseable compiled file --
    mirrors test_put_malformed_spec_missing_bounds_does_not_500's arrangement,
    but the shape defect lives in the compiled dir, not an evaluator spec."""
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()

    # Shape-invalid params block: a spec must be a dict (e.g. {"default": ...}),
    # not a bare int. effective_params() would do spec.get("default") and
    # raise AttributeError.
    (compiled_dir / "broken.json").write_text(json.dumps({
        "id": "broken",
        "principles": [{"name": "P", "requirements": [{
            "id": "BROKEN-1",
            "text": "At most {max_lines} lines",
            "params": {"max_lines": 5},
        }]}],
    }))

    project_root = tmp_path / "repo"
    project_root.mkdir()

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: str(project_root))

    with app.test_client() as c:
        resp = c.put(OVERRIDES_URL, json={"overrides": {}}, headers=_LOCALHOST)
        assert resp.status_code == 200
        assert resp.status_code != 500


def test_get_rejects_traversal_project_id(client):
    resp = client.get("/api/projects/../standards-overrides")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "bad_request"


def test_put_rejects_traversal_project_id(client):
    resp = client.put("/api/projects/../standards-overrides", json={"overrides": {}},
                      headers=_LOCALHOST)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "bad_request"
