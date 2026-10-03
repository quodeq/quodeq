"""POST /api/evaluations rejects a string flag instead of coercing it.

``bool("false")`` is ``True`` in Python, so coercing would give a client
that sends ``verifyFindings: "false"`` (or the other flags below) the
opposite of what it asked for. A non-bool flag gets a coded 400 instead.
Route-level: the guard runs before ``provider.start_evaluation`` is reached.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app
from quodeq.services.base import ActionProvider

_ORIGIN = {"Origin": "http://localhost"}
_BOOL_FIELDS = ("numerical", "verifyFindings", "perDimension", "cleanScan")


class _CountingProvider(ActionProvider):
    """Minimal provider that records whether start_evaluation was reached."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.options = None

    def list_projects(self, reports_dir):
        return {"projects": []}

    def get_project_info(self, reports_dir, project):
        return {}

    def start_evaluation(self, repo, reports_dir, options):
        self.start_calls += 1
        self.options = options
        return {"jobId": "test-job", "status": "running", "logs": []}

    def get_evaluation_status(self, job_id, reports_dir=None):
        return None

    def cancel_evaluation(self, job_id, reports_dir=None, discard_partial=False, wait_for_exit=False):
        return False

    def list_evaluations(self, *, limit=0, reports_dir=None, states=None):
        return []

    def delete_project(self, reports_dir, project):
        return False


@pytest.fixture()
def provider():
    return _CountingProvider()


@pytest.fixture()
def client(monkeypatch, provider):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    return create_app(provider).test_client()


@pytest.mark.parametrize("field", _BOOL_FIELDS)
def test_string_false_is_rejected_with_a_coded_400(client, provider, field):
    resp = client.post(
        "/api/evaluations",
        json={"repo": "/some/valid/path", field: "false"},
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert field in body["error"]
    # The guard fires before the field could be silently coerced (bool("false")
    # is True) and the evaluation started with the opposite of what was sent.
    assert provider.start_calls == 0


def test_incremental_string_false_is_rejected_with_a_coded_400(client, provider):
    resp = client.post(
        "/api/evaluations",
        json={"repo": "/some/valid/path", "incremental": "false"},
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert "incremental" in body["error"]
    assert provider.start_calls == 0


@pytest.mark.parametrize("field", _BOOL_FIELDS)
@pytest.mark.parametrize("value", [True, False])
def test_real_boolean_is_unaffected(client, provider, field, value):
    # A URL repo skips the local-path scan allowlist check, isolating this
    # test to the bool-field guard alone.
    resp = client.post(
        "/api/evaluations",
        json={"repo": "https://github.com/x/y.git", field: value},
        headers=_ORIGIN,
    )
    assert resp.status_code == 202
    assert provider.start_calls == 1


@pytest.mark.parametrize("field", (*_BOOL_FIELDS, "incremental"))
def test_json_null_is_treated_as_absent(client, provider, field):
    resp = client.post(
        "/api/evaluations",
        json={"repo": "https://github.com/x/y.git", field: None},
        headers=_ORIGIN,
    )
    assert resp.status_code == 202
    assert provider.start_calls == 1
    # null takes each flag's default, the same options as omitting it.
    opts = provider.options
    assert (opts.numerical, opts.verify_findings, opts.per_dimension, opts.clean_scan) == (
        False, True, False, False)
