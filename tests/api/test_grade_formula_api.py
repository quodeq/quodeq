"""Contract tests for /api/grade-formula endpoints."""
from __future__ import annotations

import dataclasses

import pytest

from quodeq.api.app import create_app
from quodeq.core.scoring.params import DEFAULT_PARAMS, params_to_dict
from quodeq.services import grade_formula
from tests.api.test_action_api import StubProvider

# State-changing requests require a matching Origin header (CSRF guard in
# api/security.py). The test client's default host is "localhost".
_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Disable auth by ensuring QUODEQ_API_KEY is unset so _check_auth() is a no-op."""
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


@pytest.fixture
def formula_path(tmp_path, monkeypatch):
    path = tmp_path / "grade_formula.json"
    monkeypatch.setattr(grade_formula, "grade_formula_path", lambda: path)
    return path


@pytest.fixture()
def client():
    """Flask test client backed by a StubProvider."""
    return create_app(StubProvider()).test_client()


def test_get_returns_defaults_and_is_custom_false(client, formula_path):
    resp = client.get("/api/grade-formula")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["isCustom"] is False
    assert body["current"] == params_to_dict(DEFAULT_PARAMS)
    assert body["defaults"] == params_to_dict(DEFAULT_PARAMS)


def test_put_saves_and_applies(client, formula_path, monkeypatch):
    applied = {}
    monkeypatch.setattr(
        grade_formula, "apply_to_all_runs", lambda root: applied.setdefault("n", 7) or 7,
    )
    payload = params_to_dict(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    resp = client.put("/api/grade-formula", json=payload, headers=_ORIGIN)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["isCustom"] is True
    assert body["applied"] == 7
    assert grade_formula.load_params().base_k == 0.3


def test_put_rejects_invalid_params_with_400(client, formula_path):
    payload = params_to_dict(DEFAULT_PARAMS)
    payload["baseK"] = 99.0
    resp = client.put("/api/grade-formula", json=payload, headers=_ORIGIN)
    assert resp.status_code == 400
    assert not formula_path.exists()


def test_delete_resets_to_defaults(client, formula_path, monkeypatch):
    monkeypatch.setattr(grade_formula, "apply_to_all_runs", lambda root: 0)
    grade_formula.save_params(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    resp = client.delete("/api/grade-formula", headers=_ORIGIN)
    assert resp.status_code == 200
    assert resp.get_json()["isCustom"] is False
    assert not formula_path.exists()


def test_preview_returns_404_when_no_runs(client, formula_path, monkeypatch):
    monkeypatch.setattr(grade_formula, "preview_scores", lambda root, project, params: None)
    resp = client.post(
        "/api/grade-formula/preview",
        json={"project": "nope", "params": params_to_dict(DEFAULT_PARAMS)},
        headers=_ORIGIN,
    )
    assert resp.status_code == 404


def test_preview_returns_before_after(client, formula_path, monkeypatch):
    fake = {
        "project": "p", "runId": "r1",
        "before": {"overall": {"score": 7.4, "grade": "Good"}, "dimensions": []},
        "after": {"overall": {"score": 6.8, "grade": "Adequate"}, "dimensions": []},
    }
    monkeypatch.setattr(grade_formula, "preview_scores", lambda root, project, params: fake)
    resp = client.post(
        "/api/grade-formula/preview",
        json={"project": "p", "params": params_to_dict(DEFAULT_PARAMS)},
        headers=_ORIGIN,
    )
    assert resp.status_code == 200
    assert resp.get_json() == fake


def test_preview_rejects_invalid_params(client, formula_path):
    payload = params_to_dict(DEFAULT_PARAMS)
    payload["baseK"] = 99.0
    resp = client.post(
        "/api/grade-formula/preview", json={"project": "p", "params": payload}, headers=_ORIGIN,
    )
    assert resp.status_code == 400
