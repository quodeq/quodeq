"""Cancel with discard must leave nothing behind — scoring must not run.

Split from test_cancel_discard_purge.py.

v1.6.0 bug: cancelling a run with "Discard findings" still produced a graded
run on the Overview. The cancel path scored completed dimensions BEFORE
discarding, and the status-GET background-scoring path could resurrect a
discarded run from whatever evidence survived the purge race.
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from quodeq.core.types import JobSnapshot
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from quodeq.services.filesystem import FilesystemActionProvider


class TestDiscardSkipsScoring:
    def test_discard_does_not_score_completed_evidence(self):
        """With discard_partial=True, cancel must NOT write eval reports.

        Scoring first and discarding second is how the discarded run kept a
        grade: _score_completed_evidence wrote evaluation/<dim>.json for every
        finished dim, and the discard helper then explicitly preserved them.
        """
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(
            job_id="j1", status="running",
            output_project="proj", output_run_id="run1",
        )
        with patch("quodeq.services.evaluation_mixin.score_completed_evidence") as mock_score, \
             patch("quodeq.services.evaluation_mixin._discard_run_state") as mock_discard, \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"):
            result = m.cancel_evaluation(
                "j1", reports_dir="/reports", discard_partial=True,
            )
        assert result is True
        mock_score.assert_not_called()
        mock_discard.assert_called_once()

    def test_keep_findings_still_scores(self):
        """Without discard, the cancel path keeps scoring completed dims."""
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(
            job_id="j1", status="running",
            output_project="proj", output_run_id="run1",
        )
        with patch("quodeq.services.evaluation_mixin.score_completed_evidence") as mock_score, \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"):
            result = m.cancel_evaluation("j1", reports_dir="/reports")
        assert result is True
        mock_score.assert_called_once()


class TestRouteDiscardBlocksScoringResurrection:
    """DELETE ?discard=true must pre-claim the scoring registry.

    Without the claim, the very next status GET (the UI polls every 1.5s)
    sees status == cancelled and spawns _score_completed_evidence in the
    background, re-writing eval reports for whatever evidence survives the
    purge race.
    """

    def _make_app(self):
        from quodeq.api.app import create_app

        class _Provider(FilesystemActionProvider):
            pass

        provider = MagicMock()
        provider.get_evaluation_status.return_value = JobSnapshot(
            job_id="j-disc", status="running",
            output_project="proj", output_run_id="run-d",
        )
        provider.cancel_evaluation.return_value = True
        app = create_app(provider)
        return app, provider

    @pytest.fixture(autouse=True)
    def _reset_claim_registry(self, monkeypatch):
        from quodeq.api._evaluation_routes import _scored_jobs, _scored_jobs_lock
        monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
        with _scored_jobs_lock:
            _scored_jobs.clear()
        yield
        with _scored_jobs_lock:
            _scored_jobs.clear()

    def test_get_after_discard_cancel_does_not_score(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
        app, provider = self._make_app()
        client = app.test_client()

        resp = client.delete(
            "/api/evaluations/j-disc?discard=true",
            headers={"Origin": "http://localhost"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["discarded"] is True

        # Job is now terminal; the UI's next poll arrives.
        provider.get_evaluation_status.return_value = JobSnapshot(
            job_id="j-disc", status="cancelled",
            output_project="proj", output_run_id="run-d",
        )
        scored = threading.Event()
        with patch(
            "quodeq.api._evaluation_routes.score_completed_evidence",
            side_effect=lambda *a, **k: scored.set(),
        ):
            get_resp = client.get("/api/evaluations/j-disc")
            assert get_resp.status_code == 200
            # Give a would-be background thread time to start.
            assert not scored.wait(timeout=0.3), (
                "status GET resurrected scoring for a discarded run"
            )
