"""Contract tests for /api/grade-formula endpoints."""
from __future__ import annotations

import dataclasses

import pytest
from flask import Flask

from quodeq.api._grade_formula_routes import register_grade_formula_routes
from quodeq.api.app import create_app
from quodeq.core.scoring.params import DEFAULT_PARAMS, params_to_dict
from quodeq.services import grade_formula
from quodeq.services.grade_formula_job import GradeFormulaRescorer
from tests._timeouts import budget
from tests.api.test_action_api import StubProvider


def _instant_apply(rescored=2, failed=()):
    """Fake apply_to_all_runs that finishes at once with the given outcome."""
    def _apply(root, *, progress, should_abort):
        progress(rescored, rescored)
        return grade_formula.ApplyResult(rescored=rescored, failed=list(failed))
    return _apply


@pytest.fixture
def rescore_client():
    """Bare Flask app with an injected rescorer running a fake pass.

    Every rescorer built here is stopped on teardown, so no worker thread
    outlives its test.
    """
    made = []

    def _make(apply_fn):
        app = Flask(__name__)
        app.config["TESTING"] = True
        rescorer = GradeFormulaRescorer(apply_fn)
        register_grade_formula_routes(app, rescorer=rescorer)
        made.append(rescorer)
        return app.test_client(), rescorer

    yield _make
    for rescorer in made:
        rescorer.stop()


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
    monkeypatch.setenv("QUODEQ_GRADE_FORMULA_PATH", str(path))
    return path


@pytest.fixture()
def client():
    """Flask test client backed by a StubProvider; stops the app's rescorer on teardown."""
    app = create_app(StubProvider())
    yield app.test_client()
    app.extensions["grade_formula_rescore"].stop()


def test_get_returns_defaults_and_is_custom_false(client, formula_path):
    resp = client.get("/api/grade-formula")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["isCustom"] is False
    assert body["current"] == params_to_dict(DEFAULT_PARAMS)
    assert body["defaults"] == params_to_dict(DEFAULT_PARAMS)


def test_get_carries_an_idle_rescore_on_a_fresh_app(client, formula_path):
    body = client.get("/api/grade-formula").get_json()
    assert body["rescore"] == {
        "state": "idle", "generation": 0, "appliedGeneration": 0,
        "done": 0, "total": 0, "failed": 0,
    }


def test_put_saves_and_returns_202_with_a_running_rescore(rescore_client, formula_path):
    client, _ = rescore_client(_instant_apply())
    payload = params_to_dict(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    resp = client.put("/api/grade-formula", json=payload, headers=_ORIGIN)
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["isCustom"] is True
    assert body["current"]["baseK"] == 0.3
    assert (body["rescore"]["state"], body["rescore"]["generation"]) == ("running", 1)
    assert "applied" not in body and "failed" not in body
    assert grade_formula.load_params().base_k == 0.3


def test_get_reports_the_landed_pass_with_a_failed_count(rescore_client, formula_path):
    client, rescorer = rescore_client(_instant_apply(rescored=5, failed=["run-x", "run-y"]))
    payload = params_to_dict(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    client.put("/api/grade-formula", json=payload, headers=_ORIGIN)
    assert rescorer.wait_idle(budget(5))

    body = client.get("/api/grade-formula").get_json()
    assert body["rescore"] == {
        "state": "idle", "generation": 1, "appliedGeneration": 1,
        "done": 5, "total": 5, "failed": 2,
    }


def test_put_rejects_invalid_params_with_400(client, formula_path):
    payload = params_to_dict(DEFAULT_PARAMS)
    payload["baseK"] = 99.0
    resp = client.put("/api/grade-formula", json=payload, headers=_ORIGIN)
    assert resp.status_code == 400
    assert not formula_path.exists()


def test_delete_requires_confirm_and_does_not_reset(rescore_client, formula_path):
    client, rescorer = rescore_client(_instant_apply())
    grade_formula.save_params(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    resp = client.delete("/api/grade-formula", headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "CONFIRMATION_REQUIRED"
    assert "?confirm=true" in body["error"]
    assert rescorer.snapshot().generation == 0, "no rescore without ?confirm=true"
    assert grade_formula.load_params().base_k == 0.3
    assert formula_path.exists()


def test_delete_with_confirm_resets_and_returns_202(rescore_client, formula_path):
    client, _ = rescore_client(_instant_apply())
    grade_formula.save_params(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    resp = client.delete("/api/grade-formula?confirm=true", headers=_ORIGIN)
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["isCustom"] is False
    assert body["rescore"]["generation"] == 1
    assert not formula_path.exists()


def test_invalid_put_does_not_start_a_rescore(rescore_client, formula_path):
    client, rescorer = rescore_client(_instant_apply())
    payload = params_to_dict(DEFAULT_PARAMS)
    payload["baseK"] = 99.0
    assert client.put("/api/grade-formula", json=payload, headers=_ORIGIN).status_code == 400
    assert rescorer.snapshot().generation == 0


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


def test_put_names_the_malformed_key_without_echoing_exception_text(client, formula_path):
    payload = params_to_dict(DEFAULT_PARAMS)
    payload["baseK"] = "abc"
    resp = client.put("/api/grade-formula", json=payload, headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert body["error"] == "Malformed params: baseK"
    assert not formula_path.exists()
