"""Tests for GET/PUT /api/projects/<project_id>/standards-overrides."""
import json
from pathlib import Path

import pytest

from quodeq.api.app import create_app

OVERRIDES_URL = "/api/projects/proj-1/standards-overrides"


def _write_compiled_dim(compiled_dir: Path) -> None:
    (compiled_dir / "maintainability.json").write_text(json.dumps({
        "id": "maintainability",
        "principles": [{"name": "Analyzability", "requirements": [{
            "id": "M-ANA-2",
            "text": "Functions MUST NOT exceed {max_lines} lines",
            "params": {"max_lines": {"label": "Max function lines", "type": "int",
                                     "default": 50, "min": 10, "max": 500}},
        }]}],
    }))


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture()
def client(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch):
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()
    _write_compiled_dim(compiled_dir)

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: str(project_root) if pid == "proj-1" else None)

    with app.test_client() as c:
        yield c


@pytest.fixture()
def client_without_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: None)

    with app.test_client() as c:
        yield c


def test_get_returns_empty_when_no_file(client):
    resp = client.get(OVERRIDES_URL)
    assert resp.status_code == 200
    assert resp.get_json() == {"overrides": {}, "counts": {}}


_LOCALHOST = {"Origin": "http://localhost"}


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


# ---------------------------------------------------------------------------
# Fix 3: PUT accepts overrides for params-bearing req declared only in evaluators_dir
# ---------------------------------------------------------------------------

def _write_evaluator_dim(evaluators_dir: Path) -> None:
    """Write a custom standard with its own params-bearing requirement."""
    (evaluators_dir / "custom-standard.json").write_text(json.dumps({
        "id": "custom-standard",
        "type": "custom",
        "managed": False,
        "principles": [{"name": "Custom Principle", "requirements": [{
            "id": "CUST-1",
            "text": "Custom rule MUST NOT exceed {max_items} items",
            "params": {"max_items": {"label": "Max items", "type": "int",
                                     "default": 100, "min": 1, "max": 1000}},
        }]}],
    }))


@pytest.fixture()
def client_with_custom(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch):
    """Client fixture with a custom standard in evaluators_dir."""
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()
    _write_compiled_dim(compiled_dir)

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()
    _write_evaluator_dim(evaluators)

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: str(project_root) if pid == "proj-1" else None)

    with app.test_client() as c:
        yield c


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


# ---------------------------------------------------------------------------
# Task 6: dryRun impact preview and changedDimensions
# ---------------------------------------------------------------------------

def test_dry_run_reports_changed_dimension_without_writing(client, project_root: Path):
    resp = client.put(OVERRIDES_URL + "?dryRun=true",
                      json={"overrides": {"M-ANA-2": {"max_lines": 60}}}, headers=_LOCALHOST)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["changedDimensions"] == ["maintainability"]
    assert not (project_root / ".quodeq" / "standards-overrides.json").exists()


def test_dry_run_override_equal_to_default_reports_no_change(client, project_root: Path):
    resp = client.put(OVERRIDES_URL + "?dryRun=true",
                      json={"overrides": {"M-ANA-2": {"max_lines": 50}}}, headers=_LOCALHOST)
    assert resp.status_code == 200
    assert resp.get_json()["changedDimensions"] == []


def test_dry_run_validates_like_real_put(client):
    resp = client.put(OVERRIDES_URL + "?dryRun=true",
                      json={"overrides": {"M-ANA-2": {"max_lines": 9}}}, headers=_LOCALHOST)
    assert resp.status_code == 400


def test_real_put_returns_changed_dimensions_and_writes(client, project_root: Path):
    resp = client.put(OVERRIDES_URL,
                      json={"overrides": {"M-ANA-2": {"max_lines": 60}}}, headers=_LOCALHOST)
    assert resp.status_code == 200
    assert resp.get_json()["changedDimensions"] == ["maintainability"]
    assert (project_root / ".quodeq" / "standards-overrides.json").exists()


def test_clearing_overrides_reports_reverted_dimension(client, project_root: Path):
    client.put(OVERRIDES_URL, json={"overrides": {"M-ANA-2": {"max_lines": 60}}},
               headers=_LOCALHOST)
    resp = client.put(OVERRIDES_URL, json={"overrides": {}}, headers=_LOCALHOST)
    assert resp.status_code == 200
    assert resp.get_json()["changedDimensions"] == ["maintainability"]
    assert not (project_root / ".quodeq" / "standards-overrides.json").exists()
