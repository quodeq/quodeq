"""Tests for quodeq.services.evaluation_mixin — evaluation flow and scoring."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestScoreCompletedEvidence:
    def test_no_project_or_run_id(self):
        from quodeq.services.evaluation_mixin import _score_completed_evidence
        _score_completed_evidence("/tmp/reports", {})  # should not raise

    def test_no_evidence_dir(self, tmp_path):
        from quodeq.services.evaluation_mixin import _score_completed_evidence
        _score_completed_evidence(str(tmp_path), {
            "outputProject": "proj", "outputRunId": "run1"
        })  # evidence dir doesn't exist, returns early

    def test_scores_completed_dimension(self, tmp_path):
        from quodeq.services.evaluation_mixin import _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        eval_dir = proj_dir / "evaluation"
        eval_dir.mkdir(parents=True)

        # Create a JSONL file with content and a queue file
        jsonl = evidence_dir / "security_evidence.jsonl"
        jsonl.write_text(json.dumps({"p": "P1", "t": "violation"}) + "\n")
        queue = evidence_dir / "security_queue.json"
        queue.write_text("[]")

        mock_evidence = MagicMock()
        mock_scores = {"security": 75}

        with patch("quodeq.core.evidence.parser.parse_jsonl_to_evidence", return_value=mock_evidence), \
             patch("quodeq.core.scoring.engine.score_evidence", return_value=mock_scores), \
             patch("quodeq.analysis.report.write_dimension_report"):
            _score_completed_evidence(str(tmp_path), {
                "outputProject": "proj", "outputRunId": "run1"
            })

    def test_skips_already_scored(self, tmp_path):
        from quodeq.services.evaluation_mixin import _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        eval_dir = proj_dir / "evaluation"
        eval_dir.mkdir(parents=True)

        jsonl = evidence_dir / "security_evidence.jsonl"
        jsonl.write_text("data\n")
        queue = evidence_dir / "security_queue.json"
        queue.write_text("[]")
        # Already scored
        (eval_dir / "security.json").write_text("{}")

        with patch("quodeq.core.evidence.parser.parse_jsonl_to_evidence") as mock_parse:
            _score_completed_evidence(str(tmp_path), {
                "outputProject": "proj", "outputRunId": "run1"
            })
            mock_parse.assert_not_called()

    def test_skips_empty_jsonl(self, tmp_path):
        from quodeq.services.evaluation_mixin import _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (proj_dir / "evaluation").mkdir(parents=True)

        jsonl = evidence_dir / "security_evidence.jsonl"
        jsonl.write_text("")
        queue = evidence_dir / "security_queue.json"
        queue.write_text("[]")

        with patch("quodeq.core.evidence.parser.parse_jsonl_to_evidence") as mock_parse:
            _score_completed_evidence(str(tmp_path), {
                "outputProject": "proj", "outputRunId": "run1"
            })
            mock_parse.assert_not_called()

    def test_skips_no_queue_file(self, tmp_path):
        from quodeq.services.evaluation_mixin import _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (proj_dir / "evaluation").mkdir(parents=True)

        jsonl = evidence_dir / "security_evidence.jsonl"
        jsonl.write_text("data\n")
        # No queue file

        with patch("quodeq.core.evidence.parser.parse_jsonl_to_evidence") as mock_parse:
            _score_completed_evidence(str(tmp_path), {
                "outputProject": "proj", "outputRunId": "run1"
            })
            mock_parse.assert_not_called()

    def test_handles_scoring_exception(self, tmp_path):
        from quodeq.services.evaluation_mixin import _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (proj_dir / "evaluation").mkdir(parents=True)

        jsonl = evidence_dir / "dim_evidence.jsonl"
        jsonl.write_text("data\n")
        queue = evidence_dir / "dim_queue.json"
        queue.write_text("[]")

        with patch("quodeq.core.evidence.parser.parse_jsonl_to_evidence", side_effect=ValueError("parse fail")):
            _score_completed_evidence(str(tmp_path), {
                "outputProject": "proj", "outputRunId": "run1"
            })  # should not raise

    def test_handles_none_evidence(self, tmp_path):
        from quodeq.services.evaluation_mixin import _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (proj_dir / "evaluation").mkdir(parents=True)

        jsonl = evidence_dir / "dim_evidence.jsonl"
        jsonl.write_text("data\n")
        queue = evidence_dir / "dim_queue.json"
        queue.write_text("[]")

        with patch("quodeq.core.evidence.parser.parse_jsonl_to_evidence", return_value=None), \
             patch("quodeq.core.scoring.engine.score_evidence") as mock_score:
            _score_completed_evidence(str(tmp_path), {
                "outputProject": "proj", "outputRunId": "run1"
            })
            mock_score.assert_not_called()


class TestFsEvaluationMixinMethods:
    def _make_mixin(self):
        from quodeq.services.evaluation_mixin import FsEvaluationMixin
        from quodeq.services.jobs import JobManager

        class TestProvider(FsEvaluationMixin):
            def __init__(self):
                self._jobs = MagicMock(spec=JobManager)
                self._dispatcher = None

        return TestProvider()

    def test_get_evaluation_status(self):
        mixin = self._make_mixin()
        mixin._jobs.get_job.return_value = {"status": "running"}
        result = mixin.get_evaluation_status("job-1")
        assert result == {"status": "running"}

    def test_list_evaluations(self):
        mixin = self._make_mixin()
        mixin._jobs.list_jobs.return_value = [{"id": "j1"}, {"id": "j2"}]
        result = mixin.list_evaluations()
        assert len(result) == 2

    def test_cancel_evaluation(self):
        mixin = self._make_mixin()
        mixin._jobs.cancel_job.return_value = True
        mixin._jobs.get_job.return_value = MagicMock(output_project="proj", output_run_id="run1")
        with patch("quodeq.services.evaluation_mixin._score_completed_evidence"):
            result = mixin.cancel_evaluation("job-1", "/tmp/reports")
            assert result is True

    def test_score_failed_evaluation_not_found(self):
        mixin = self._make_mixin()
        mixin._jobs.get_job.return_value = None
        result = mixin.score_failed_evaluation("job-1", "/tmp/reports")
        assert result is False

    def test_score_failed_evaluation_wrong_status(self):
        mixin = self._make_mixin()
        job = {"status": "running"}
        mixin._jobs.get_job.return_value = job
        result = mixin.score_failed_evaluation("job-1", "/tmp/reports")
        assert result is False

    def test_score_failed_evaluation_success(self):
        mixin = self._make_mixin()
        job = MagicMock()
        job.get.return_value = "failed"
        job.__getitem__ = MagicMock()
        mixin._jobs.get_job.return_value = job
        with patch("quodeq.services.evaluation_mixin._score_completed_evidence"):
            result = mixin.score_failed_evaluation("job-1", "/tmp/reports")
            assert result is True

    def test_dispatcher_default(self):
        mixin = self._make_mixin()
        from quodeq.services.evaluation_mixin import SubprocessDispatcher
        d = mixin.dispatcher
        assert isinstance(d, SubprocessDispatcher)
