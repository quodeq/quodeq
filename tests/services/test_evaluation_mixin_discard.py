"""Tests for evaluation_mixin.py — cancel discard-partial cleanup and score_failed_evaluation.

Split from test_evaluation_mixin.py."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from quodeq.core.types.job import JobSnapshot
from quodeq.services.evaluation_mixin import (
    FsEvaluationMixin,
    _discard_run_state,
)


class TestDiscardRunState:
    def _make_run(self, tmp_path: Path, *, dims: list[str], scored: list[str]) -> Path:
        evidence = tmp_path / "reports" / "proj" / "run1" / "evidence"
        evaluation = tmp_path / "reports" / "proj" / "run1" / "evaluation"
        evidence.mkdir(parents=True)
        evaluation.mkdir(parents=True)
        for dim in dims:
            (evidence / f"{dim}_queue.json").write_text("{}")
            (evidence / f"{dim}_fingerprint.json").write_text("{}")
        for dim in scored:
            (evaluation / f"{dim}.json").write_text("{}")
        return tmp_path / "reports"

    def test_wipes_scored_and_unscored_dim_state(self, tmp_path: Path):
        # Discard means the run never happened: scratch for scored dims is
        # wiped just like in-flight ones (the run dir itself is removed by
        # the provider right after).
        reports = self._make_run(
            tmp_path, dims=["security", "usability"], scored=["security"],
        )
        _discard_run_state(
            str(reports), {"outputProject": "proj", "outputRunId": "run1"},
        )
        evidence = reports / "proj" / "run1" / "evidence"
        assert not (evidence / "security_queue.json").exists()
        assert not (evidence / "security_fingerprint.json").exists()
        assert not (evidence / "usability_queue.json").exists()
        assert not (evidence / "usability_fingerprint.json").exists()

    def test_no_evaluation_dir_wipes_everything(self, tmp_path: Path):
        # Run cancelled before any dim could finalise — every queue/fingerprint
        # is in-flight and gets wiped.
        evidence = tmp_path / "reports" / "proj" / "run1" / "evidence"
        evidence.mkdir(parents=True)
        (evidence / "security_queue.json").write_text("{}")
        (evidence / "security_fingerprint.json").write_text("{}")
        (evidence / "usability_queue.json").write_text("{}")
        (evidence / "usability_fingerprint.json").write_text("{}")

        _discard_run_state(
            str(tmp_path / "reports"),
            {"outputProject": "proj", "outputRunId": "run1"},
        )
        assert list(evidence.iterdir()) == []

    def test_missing_evidence_dir_is_silent(self, tmp_path: Path):
        # A truly empty run dir shouldn't raise.
        _discard_run_state(
            str(tmp_path),
            {"outputProject": "ghost", "outputRunId": "ghost"},
        )

    def test_missing_project_or_run_id_is_silent(self, tmp_path: Path):
        # Defensive: a malformed job dict should noop, not throw.
        _discard_run_state(str(tmp_path), {})
        _discard_run_state(str(tmp_path), {"outputProject": "p"})


class TestScoreFailedEvaluation:
    def test_returns_false_for_running_job(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.get_job.return_value = JobSnapshot(job_id="j1", status="running")
        assert m.score_failed_evaluation("j1", "/reports") is False

    def test_returns_false_for_missing_job(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.get_job.return_value = None
        assert m.score_failed_evaluation("j1", "/reports") is False


# ---------------------------------------------------------------------------
# _score_completed_evidence
# ---------------------------------------------------------------------------


