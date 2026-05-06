"""API request payload compatibility for the incremental → clean_scan rename."""
import logging
from unittest.mock import patch
import pytest

from quodeq.api._evaluation_helpers import _build_evaluation_options
import quodeq.api._evaluation_helpers as _helpers_mod
from quodeq.api.app import create_app
from quodeq.services.base import ActionProvider, EvaluationOptions


class _StubProvider(ActionProvider):
    """Minimal provider for route-level tests."""

    def list_projects(self, reports_dir):
        return {"projects": []}

    def get_project_info(self, reports_dir, project):
        return {}

    def start_evaluation(self, repo, reports_dir, options):
        return {"jobId": "test-job", "status": "running", "logs": []}

    def get_evaluation_status(self, job_id, reports_dir=None):
        return None

    def cancel_evaluation(self, job_id, reports_dir=None, discard_partial=False):
        return False

    def list_evaluations(self, *, limit=0, reports_dir=None, states=None):
        return []

    def delete_project(self, reports_dir, project):
        return False


@pytest.fixture()
def client(monkeypatch):
    """Flask test client for route-level tests (auth disabled)."""
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    return create_app(_StubProvider()).test_client()


def test_clean_scan_field_default_false():
    opts = _build_evaluation_options({})
    assert opts.clean_scan is False


def test_clean_scan_field_explicit_true():
    opts = _build_evaluation_options({"cleanScan": True})
    assert opts.clean_scan is True


def test_legacy_incremental_false_maps_to_clean_scan_true():
    """Legacy `incremental: false` (old "ignore cache") maps to `clean_scan: true`.

    Inverted semantics: the old flag was opt-in; the new flag is opt-out.
    """
    with patch.object(_helpers_mod._logger, "warning") as mock_warn:
        opts = _build_evaluation_options({"incremental": False})
    assert opts.clean_scan is True
    # Deprecation warning should fire on the helper module's logger.
    assert mock_warn.called, "Expected a deprecation warning for legacy `incremental` field"
    warn_msg = mock_warn.call_args[0][0]
    assert "deprecated" in warn_msg.lower()
    assert "incremental" in warn_msg.lower()


def test_legacy_incremental_true_maps_to_clean_scan_false():
    """Legacy `incremental: true` (old "use cache") maps to `clean_scan: false`."""
    with patch.object(_helpers_mod._logger, "warning") as mock_warn:
        opts = _build_evaluation_options({"incremental": True})
    assert opts.clean_scan is False
    assert mock_warn.called, "Expected a deprecation warning for legacy `incremental` field"
    warn_msg = mock_warn.call_args[0][0]
    assert "deprecated" in warn_msg.lower()
    assert "incremental" in warn_msg.lower()


def test_conflicting_fields_rejected():
    """Sending both fields is a ValueError — we don't guess intent."""
    with pytest.raises(ValueError, match="cannot be combined"):
        _build_evaluation_options({"incremental": True, "cleanScan": True})


def test_conflicting_fields_rejected_even_when_values_align():
    """Even semantically-aligned values are rejected — explicit is safer."""
    with pytest.raises(ValueError, match="cannot be combined"):
        # incremental=True (use cache) aligns with cleanScan=False (use cache),
        # but having both is still ambiguous payload state.
        _build_evaluation_options({"incremental": True, "cleanScan": False})


def test_route_returns_400_with_specific_message_on_field_conflict(client):
    """Route surfaces the conflict message, not 'Invalid repository'."""
    # The CSRF check requires an Origin header matching the test server host.
    response = client.post(
        "/api/evaluations",
        json={
            "repo": "/some/valid/path",
            "incremental": True,
            "cleanScan": True,
        },
        headers={"Origin": "http://localhost"},
    )
    assert response.status_code == 400
    body = response.get_json() or {}
    msg = (body.get("error") or body.get("message") or "").lower()
    assert "cannot be combined" in msg or "cleanscan" in msg, (
        f"Expected conflict message; got: {body!r}"
    )
