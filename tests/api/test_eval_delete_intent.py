"""DELETE /api/evaluations/<job_id> must honor explicit client intent.

The endpoint used to infer cancel-vs-delete purely from the momentary
snapshot status, so a run finishing while the cancel dialog was open (or a
double-clicked cancel) fell through to the permanent-purge branch and
erased a run the user explicitly chose to keep.

With ?intent=cancel the request can never purge: if the run is already
terminal it returns 409 and the run stays. With ?intent=delete a run that
is unexpectedly still running returns 409 instead of being silently
cancelled. Requests without intent keep the legacy status-based behavior.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quodeq.api.app import create_app
from quodeq.core.types import JobSnapshot

ORIGIN = {"Origin": "http://localhost"}


def _make_client(status: str):
    provider = MagicMock()
    provider.get_evaluation_status.return_value = JobSnapshot(
        job_id="j1", status=status,
        output_project="proj", output_run_id="run-1",
    )
    provider.cancel_evaluation.return_value = True
    provider.delete_evaluation.return_value = True
    app = create_app(provider)
    return app.test_client(), provider


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))


class TestCancelIntent:
    def test_cancel_intent_on_running_job_cancels(self):
        client, provider = _make_client("running")
        resp = client.delete("/api/evaluations/j1?intent=cancel", headers=ORIGIN)
        assert resp.status_code == 200
        assert resp.get_json()["action"] == "cancelled"
        provider.cancel_evaluation.assert_called_once()
        provider.delete_evaluation.assert_not_called()

    def test_cancel_intent_never_purges_a_finished_run(self):
        """The dialog-open race: run finished before the DELETE arrived."""
        client, provider = _make_client("done")
        resp = client.delete("/api/evaluations/j1?intent=cancel", headers=ORIGIN)
        assert resp.status_code == 409
        provider.delete_evaluation.assert_not_called()
        provider.cancel_evaluation.assert_not_called()

    def test_cancel_intent_never_purges_a_just_cancelled_run(self):
        """The double-click race: first cancel flipped the status already."""
        client, provider = _make_client("cancelled")
        resp = client.delete(
            "/api/evaluations/j1?intent=cancel&discard=true", headers=ORIGIN,
        )
        assert resp.status_code == 409
        provider.delete_evaluation.assert_not_called()


class TestDeleteIntent:
    def test_delete_intent_on_finished_run_deletes(self):
        client, provider = _make_client("done")
        resp = client.delete("/api/evaluations/j1?intent=delete", headers=ORIGIN)
        assert resp.status_code == 200
        assert resp.get_json()["action"] == "deleted"
        provider.delete_evaluation.assert_called_once()

    def test_delete_intent_refuses_a_running_run(self):
        """Stale client row: the run is actually still running. Refuse
        instead of silently cancelling under a delete request."""
        client, provider = _make_client("running")
        resp = client.delete("/api/evaluations/j1?intent=delete", headers=ORIGIN)
        assert resp.status_code == 409
        provider.cancel_evaluation.assert_not_called()
        provider.delete_evaluation.assert_not_called()


class TestLegacyNoIntent:
    def test_running_without_intent_cancels(self):
        client, provider = _make_client("running")
        resp = client.delete("/api/evaluations/j1", headers=ORIGIN)
        assert resp.status_code == 200
        assert resp.get_json()["action"] == "cancelled"

    def test_finished_without_intent_deletes(self):
        client, provider = _make_client("done")
        resp = client.delete("/api/evaluations/j1", headers=ORIGIN)
        assert resp.status_code == 200
        assert resp.get_json()["action"] == "deleted"
