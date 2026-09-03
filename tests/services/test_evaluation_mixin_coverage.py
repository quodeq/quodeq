"""Tests for quodeq.services.evaluation_mixin — evaluation flow and scoring."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.core.types.job import JobSnapshot


class TestScoreCompletedEvidence:
    def test_no_project_or_run_id(self):
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
        _score_completed_evidence("/tmp/reports", {})  # should not raise

    def test_no_evidence_dir(self, tmp_path):
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
        _score_completed_evidence(str(tmp_path), {
            "outputProject": "proj", "outputRunId": "run1"
        })  # evidence dir doesn't exist, returns early

    def test_scores_completed_dimension(self, tmp_path):
        """Real injection: score_run holds import-time bindings for parser/
        scorer/reporter, so patching their DEFINITION modules (the old
        approach) never reached them and write_dimension_report ran for
        real against MagicMock args. Injecting via the ``parser``/``scorer``/
        ``reporter`` kwargs actually intercepts the calls."""
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
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
        fake_params = object()  # sentinel: prove the value threaded through is
        # what load_params() returned, not a self-referential readback of the
        # mock's own recorded call (fake_scorer.call_args.kwargs["params"]
        # always equals itself regardless of what score_completed_evidence
        # actually passed).
        fake_parser = MagicMock(return_value=mock_evidence)
        fake_scorer = MagicMock(return_value=mock_scores)
        fake_reporter = MagicMock()

        with patch("quodeq.services.score_run.load_params", return_value=fake_params):
            _score_completed_evidence(
                str(tmp_path), {"outputProject": "proj", "outputRunId": "run1"},
                parser=fake_parser, scorer=fake_scorer, reporter=fake_reporter,
            )

        fake_parser.assert_called_once()
        assert fake_parser.call_args.args[0] == jsonl
        fake_scorer.assert_called_once_with(mock_evidence, mode="numerical", params=fake_params)
        fake_reporter.assert_called_once_with(mock_evidence, mock_scores, "security", eval_dir)

    def test_skips_already_scored(self, tmp_path):
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
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

        fake_parser = MagicMock()
        _score_completed_evidence(
            str(tmp_path), {"outputProject": "proj", "outputRunId": "run1"},
            parser=fake_parser,
        )
        fake_parser.assert_not_called()

    def test_skips_empty_jsonl(self, tmp_path):
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (proj_dir / "evaluation").mkdir(parents=True)

        jsonl = evidence_dir / "security_evidence.jsonl"
        jsonl.write_text("")
        queue = evidence_dir / "security_queue.json"
        queue.write_text("[]")

        fake_parser = MagicMock()
        _score_completed_evidence(
            str(tmp_path), {"outputProject": "proj", "outputRunId": "run1"},
            parser=fake_parser,
        )
        fake_parser.assert_not_called()

    def test_skips_no_queue_file(self, tmp_path):
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (proj_dir / "evaluation").mkdir(parents=True)

        jsonl = evidence_dir / "security_evidence.jsonl"
        jsonl.write_text("data\n")
        # No queue file

        fake_parser = MagicMock()
        _score_completed_evidence(
            str(tmp_path), {"outputProject": "proj", "outputRunId": "run1"},
            parser=fake_parser,
        )
        fake_parser.assert_not_called()

    def test_handles_scoring_exception(self, tmp_path):
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (proj_dir / "evaluation").mkdir(parents=True)

        jsonl = evidence_dir / "dim_evidence.jsonl"
        jsonl.write_text("data\n")
        queue = evidence_dir / "dim_queue.json"
        queue.write_text("[]")

        fake_parser = MagicMock(side_effect=ValueError("parse fail"))
        _score_completed_evidence(
            str(tmp_path), {"outputProject": "proj", "outputRunId": "run1"},
            parser=fake_parser,
        )  # should not raise
        fake_parser.assert_called_once()

    def test_handles_none_evidence(self, tmp_path):
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
        proj_dir = tmp_path / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (proj_dir / "evaluation").mkdir(parents=True)

        jsonl = evidence_dir / "dim_evidence.jsonl"
        jsonl.write_text("data\n")
        queue = evidence_dir / "dim_queue.json"
        queue.write_text("[]")

        fake_parser = MagicMock(return_value=None)
        fake_scorer = MagicMock()
        _score_completed_evidence(
            str(tmp_path), {"outputProject": "proj", "outputRunId": "run1"},
            parser=fake_parser, scorer=fake_scorer,
        )
        fake_parser.assert_called_once()
        fake_scorer.assert_not_called()


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
        with patch("quodeq.services.evaluation_mixin.score_completed_evidence"):
            result = mixin.cancel_evaluation("job-1", "/tmp/reports")
            assert result is True

    def test_score_failed_evaluation_not_found(self):
        mixin = self._make_mixin()
        mixin._jobs.get_job.return_value = None
        result = mixin.score_failed_evaluation("job-1", "/tmp/reports")
        assert result is False

    def test_score_failed_evaluation_wrong_status(self):
        mixin = self._make_mixin()
        job = JobSnapshot(job_id="job-1", status="running")
        mixin._jobs.get_job.return_value = job
        result = mixin.score_failed_evaluation("job-1", "/tmp/reports")
        assert result is False

    def test_score_failed_evaluation_success(self):
        mixin = self._make_mixin()
        job = JobSnapshot(job_id="job-1", status="failed")
        mixin._jobs.get_job.return_value = job
        with patch("quodeq.services.evaluation_mixin.score_completed_evidence"):
            result = mixin.score_failed_evaluation("job-1", "/tmp/reports")
            assert result is True

    def test_dispatcher_default(self):
        mixin = self._make_mixin()
        from quodeq.services.evaluation_mixin import SubprocessDispatcher
        d = mixin.dispatcher
        assert isinstance(d, SubprocessDispatcher)
