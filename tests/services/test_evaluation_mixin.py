"""Tests for evaluation_mixin.py — command building, env building, dispatch, scoring."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from quodeq.core.types import JobSnapshot
from quodeq.services.base import EvaluationOptions, _DEFAULT_MAX_SUBAGENTS, _DEFAULT_POOL_BUDGET
from quodeq.services.evaluation_mixin import (
    FsEvaluationMixin,
    SubprocessDispatcher,
    _build_evaluate_cmd,
    _register_project,
    _score_completed_evidence,
)


# ---------------------------------------------------------------------------
# _build_evaluate_cmd
# ---------------------------------------------------------------------------


class TestBuildEvaluateCmd:
    def test_basic_command(self, tmp_path: Path):
        opts = EvaluationOptions()
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path / "reports"))
        assert cmd[0] == sys.executable
        assert "-m" in cmd
        assert "quodeq.cli" in cmd
        assert "evaluate" in cmd
        # -o should point to resolved reports dir
        assert "-o" in cmd

    def test_repo_url_passed_as_is(self, tmp_path: Path):
        opts = EvaluationOptions()
        cmd = _build_evaluate_cmd("https://github.com/org/repo.git", opts, str(tmp_path))
        assert "https://github.com/org/repo.git" in cmd

    def test_dimensions_list(self, tmp_path: Path):
        opts = EvaluationOptions(dimensions=["security", "performance"])
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path))
        assert "-d" in cmd
        idx = cmd.index("-d")
        assert cmd[idx + 1] == "security,performance"

    def test_dimensions_string(self, tmp_path: Path):
        opts = EvaluationOptions(dimensions="security")
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path))
        assert "-d" in cmd
        idx = cmd.index("-d")
        assert cmd[idx + 1] == "security"

    def test_numerical_mode(self, tmp_path: Path):
        opts = EvaluationOptions(numerical=True)
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path))
        assert "-m" in cmd
        assert "numerical" in cmd

    def test_custom_subagents(self, tmp_path: Path):
        opts = EvaluationOptions(max_subagents=10)
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path))
        assert "--n-subagents" in cmd
        assert "10" in cmd

    def test_default_subagents_not_added(self, tmp_path: Path):
        opts = EvaluationOptions(max_subagents=_DEFAULT_MAX_SUBAGENTS)
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path))
        assert "--n-subagents" not in cmd

    def test_incremental_flag(self, tmp_path: Path):
        opts = EvaluationOptions(incremental=True)
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path))
        assert "--incremental" in cmd


# ---------------------------------------------------------------------------
# _build_eval_env
# ---------------------------------------------------------------------------


class TestBuildEvalEnv:
    def _mixin(self):
        m = FsEvaluationMixin()
        return m

    def test_python_unbuffered(self):
        m = self._mixin()
        env = m._build_eval_env("/repo", EvaluationOptions(), env={})
        assert env["PYTHONUNBUFFERED"] == "1"

    @patch("quodeq.services.evaluation_mixin.get_ai_cmd", return_value="claude")
    @patch("quodeq.services.evaluation_mixin.get_ai_model", return_value="sonnet")
    def test_ai_cmd_and_model(self, mock_model, mock_cmd):
        m = self._mixin()
        env = m._build_eval_env("/repo", EvaluationOptions(), env={})
        assert env["AI_CMD"] == "claude"
        assert env["AI_MODEL"] == "sonnet"
        assert env["SUBAGENT_MODEL"] == "sonnet"

    def test_explicit_options_override(self):
        m = self._mixin()
        opts = EvaluationOptions(ai_cmd="codex", ai_model="gpt-4", subagent_model="gpt-3.5")
        env = m._build_eval_env("/repo", opts, env={})
        assert env["AI_CMD"] == "codex"
        assert env["AI_MODEL"] == "gpt-4"
        assert env["SUBAGENT_MODEL"] == "gpt-3.5"

    def test_no_verify(self):
        m = self._mixin()
        opts = EvaluationOptions(verify_findings=False)
        env = m._build_eval_env("/repo", opts, env={})
        assert env.get("QUODEQ_NO_VERIFY") == "1"

    def test_verify_findings_default_no_env(self):
        m = self._mixin()
        opts = EvaluationOptions(verify_findings=True)
        env = m._build_eval_env("/repo", opts, env={})
        assert "QUODEQ_NO_VERIFY" not in env

    def test_custom_pool_budget(self):
        m = self._mixin()
        opts = EvaluationOptions(pool_budget=1200)
        env = m._build_eval_env("/repo", opts, env={})
        assert env["QUODEQ_POOL_BUDGET"] == "1200"

    def test_default_pool_budget_not_set(self):
        m = self._mixin()
        opts = EvaluationOptions(pool_budget=_DEFAULT_POOL_BUDGET)
        env = m._build_eval_env("/repo", opts, env={})
        assert "QUODEQ_POOL_BUDGET" not in env

    def test_per_dimension(self):
        m = self._mixin()
        opts = EvaluationOptions(per_dimension=True)
        env = m._build_eval_env("/repo", opts, env={})
        assert env["QUODEQ_NO_CONSOLIDATE"] == "1"

    def test_context_size(self):
        m = self._mixin()
        opts = EvaluationOptions(context_size=128000)
        env = m._build_eval_env("/repo", opts, env={})
        assert env["QUODEQ_CONTEXT_SIZE"] == "128000"

    def test_zero_context_size_not_set(self):
        m = self._mixin()
        opts = EvaluationOptions(context_size=0)
        env = m._build_eval_env("/repo", opts, env={})
        assert "QUODEQ_CONTEXT_SIZE" not in env


# ---------------------------------------------------------------------------
# SubprocessDispatcher
# ---------------------------------------------------------------------------


class TestSubprocessDispatcher:
    def test_delegates_to_job_manager(self):
        mock_mgr = MagicMock()
        expected = JobSnapshot(job_id="j1", status="running")
        mock_mgr.start_job.return_value = expected
        dispatcher = SubprocessDispatcher(mock_mgr)
        result = dispatcher.dispatch(["cmd"], cwd="/tmp", env={"A": "1"})
        assert result == expected
        mock_mgr.start_job.assert_called_once_with(["cmd"], cwd="/tmp", env={"A": "1"})


# ---------------------------------------------------------------------------
# FsEvaluationMixin.dispatcher property
# ---------------------------------------------------------------------------


class TestDispatcherProperty:
    def test_returns_custom_dispatcher(self):
        m = FsEvaluationMixin()
        custom = MagicMock()
        m._dispatcher = custom
        assert m.dispatcher is custom

    def test_returns_subprocess_dispatcher_by_default(self):
        m = FsEvaluationMixin()
        m._dispatcher = None
        m._jobs = MagicMock()
        d = m.dispatcher
        assert isinstance(d, SubprocessDispatcher)


# ---------------------------------------------------------------------------
# start_evaluation
# ---------------------------------------------------------------------------


class TestStartEvaluation:
    def _setup_mixin(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._dispatcher = MagicMock()
        m._dispatcher.dispatch.return_value = JobSnapshot(job_id="j1", status="running")
        return m

    @patch("quodeq.services.evaluation_mixin._register_project")
    @patch("quodeq.services.evaluation_mixin.is_valid_repo_url", return_value=True)
    def test_start_with_url(self, mock_valid, mock_reg):
        m = self._setup_mixin()
        opts = EvaluationOptions()
        snap = m.start_evaluation("https://github.com/org/repo.git", "/reports", opts)
        assert snap.job_id == "j1"
        m._dispatcher.dispatch.assert_called_once()

    @patch("quodeq.services.evaluation_mixin._register_project")
    def test_start_with_local_dir(self, mock_reg, tmp_path: Path):
        m = self._setup_mixin()
        opts = EvaluationOptions()
        snap = m.start_evaluation(str(tmp_path), str(tmp_path / "reports"), opts)
        assert snap.job_id == "j1"

    @patch("quodeq.services.evaluation_mixin.is_valid_repo_url", return_value=False)
    def test_invalid_url_raises(self, mock_valid):
        m = self._setup_mixin()
        opts = EvaluationOptions()
        with pytest.raises(ValueError, match="Invalid repository URL"):
            m.start_evaluation("https://bad-url", "/reports", opts)

    def test_nonexistent_local_path_raises(self):
        m = self._setup_mixin()
        opts = EvaluationOptions()
        with pytest.raises(FileNotFoundError, match="Repository not found"):
            m.start_evaluation("/nonexistent/path", "/reports", opts)

    @patch("quodeq.services.evaluation_mixin._register_project")
    def test_local_file_walks_up_to_git_root(self, mock_reg, tmp_path: Path):
        """When repo arg is a file, cwd should be the enclosing git root."""
        git_root = tmp_path / "repo"
        git_root.mkdir()
        (git_root / ".git").mkdir()
        sub = git_root / "src"
        sub.mkdir()
        f = sub / "main.py"
        f.write_text("pass")

        m = self._setup_mixin()
        opts = EvaluationOptions()
        m.start_evaluation(str(f), str(tmp_path / "reports"), opts)
        call_kwargs = m._dispatcher.dispatch.call_args
        assert call_kwargs.kwargs["cwd"] == str(git_root) or call_kwargs[1]["cwd"] == str(git_root)


# ---------------------------------------------------------------------------
# cancel_evaluation / score_failed_evaluation
# ---------------------------------------------------------------------------


class TestCancelEvaluation:
    def test_cancel_calls_job_manager(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(
            job_id="j1", status="running",
            output_project="proj", output_run_id="run1",
        )
        with patch("quodeq.services.evaluation_mixin._score_completed_evidence") as mock_score:
            result = m.cancel_evaluation("j1", reports_dir="/reports")
        assert result is True
        mock_score.assert_called_once()

    def test_cancel_without_reports_dir(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(job_id="j1", status="running")
        result = m.cancel_evaluation("j1")
        assert result is True

    def test_cancel_scores_external_jobs_via_get_evaluation_status(self):
        """External (ext-) cancels must still score completed dimensions.

        Before this refactor, cancel_evaluation used self._jobs.get_job which
        returns None for ext- ids after Plan B2, so the scoring block was dead
        for externals. Now it goes through self.get_evaluation_status, which
        the FilesystemActionProvider overrides to resolve ext- ids via the
        SQLite index. This test mocks that override pattern on the mixin
        itself.
        """
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        # Simulate Plan B2 behavior: JobManager.get_job returns None for ext-.
        m._jobs.get_job.return_value = None
        # Simulate the FilesystemActionProvider override: get_evaluation_status
        # resolves ext- via the index and returns a real snapshot.
        ext_snapshot = JobSnapshot(
            job_id="ext-run-42", status="running",
            output_project="proj-uuid", output_run_id="run-42",
        )
        with patch.object(FsEvaluationMixin, "get_evaluation_status", return_value=ext_snapshot), \
             patch("quodeq.services.evaluation_mixin._score_completed_evidence") as mock_score:
            result = m.cancel_evaluation("ext-run-42", reports_dir="/reports")
        assert result is True
        mock_score.assert_called_once()
        # Scoring was passed the snapshot's project/run ids, proving it came
        # from get_evaluation_status (not the dead get_job path).
        call_args = mock_score.call_args
        assert call_args.args[0] == "/reports"
        assert call_args.args[1]["outputProject"] == "proj-uuid"
        assert call_args.args[1]["outputRunId"] == "run-42"


class TestScoreFailedEvaluation:
    def test_returns_false_for_running_job(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.get_job.return_value = {"status": "running"}
        assert m.score_failed_evaluation("j1", "/reports") is False

    def test_returns_false_for_missing_job(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.get_job.return_value = None
        assert m.score_failed_evaluation("j1", "/reports") is False


# ---------------------------------------------------------------------------
# _score_completed_evidence
# ---------------------------------------------------------------------------


class TestScoreCompletedEvidence:
    def test_noop_without_project(self):
        _score_completed_evidence("/reports", {})  # should not raise

    def test_noop_without_run_id(self):
        _score_completed_evidence("/reports", {"outputProject": "proj"})

    def test_noop_without_evidence_dir(self, tmp_path: Path):
        reports = tmp_path / "reports"
        reports.mkdir()
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })  # evidence dir does not exist

    def test_skips_already_scored(self, tmp_path: Path):
        reports = tmp_path / "reports"
        proj_dir = reports / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        eval_dir = proj_dir / "evaluation"
        evidence_dir.mkdir(parents=True)
        eval_dir.mkdir(parents=True)
        # Create evidence + already-existing eval
        (evidence_dir / "security_evidence.jsonl").write_text('{"finding": 1}\n')
        (evidence_dir / "security_queue.json").write_text("[]")
        (eval_dir / "security.json").write_text("{}")
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })
        # Should not crash and existing eval remains

    def test_skips_empty_evidence(self, tmp_path: Path):
        reports = tmp_path / "reports"
        evidence_dir = reports / "proj" / "run1" / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "security_evidence.jsonl").write_text("")
        (evidence_dir / "security_queue.json").write_text("[]")
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })

    def test_skips_without_queue_file(self, tmp_path: Path):
        reports = tmp_path / "reports"
        evidence_dir = reports / "proj" / "run1" / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "security_evidence.jsonl").write_text('{"f": 1}\n')
        # No queue file
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })


# ---------------------------------------------------------------------------
# list_evaluations
# ---------------------------------------------------------------------------


class TestListEvaluations:
    def test_delegates_to_job_manager(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.list_jobs.return_value = []
        assert m.list_evaluations() == []
