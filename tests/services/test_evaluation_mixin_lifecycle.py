"""Tests for evaluation_mixin.py — start_evaluation / cancel_evaluation lifecycle.

Split from test_evaluation_mixin.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.core.types import JobSnapshot
from quodeq.services.base import (
    EvaluationOptions,
)
from quodeq.services.evaluation_mixin import (
    FsEvaluationMixin,
    _wait_for_terminal_status,
)
from tests._timeouts import budget


class TestStartEvaluation:
    def _setup_mixin(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._dispatcher = MagicMock()
        m._dispatcher.dispatch.return_value = JobSnapshot(job_id="j1", status="running")
        return m

    def test_url_input_rejected(self):
        """Clone-on-add (A4): start_evaluation refuses URLs; clone happens at registration."""
        m = self._setup_mixin()
        opts = EvaluationOptions()
        with pytest.raises(ValueError, match="not supported"):
            m.start_evaluation("https://github.com/org/repo.git", "/reports", opts)
        m._dispatcher.dispatch.assert_not_called()

    @patch("quodeq.services.evaluation_mixin.register_project")
    def test_start_with_local_dir(self, mock_reg, tmp_path: Path):
        m = self._setup_mixin()
        opts = EvaluationOptions()
        snap = m.start_evaluation(str(tmp_path), str(tmp_path / "reports"), opts)
        assert snap.job_id == "j1"

    @patch("quodeq.services.evaluation_mixin.register_project")
    def test_start_passes_time_limit_to_dispatcher(self, mock_reg, tmp_path: Path):
        # The job snapshot is the only channel through which the progress
        # route and the UI can learn the run's budget.
        m = self._setup_mixin()
        opts = EvaluationOptions(time_limit=900)
        m.start_evaluation(str(tmp_path), str(tmp_path / "reports"), opts)
        assert m._dispatcher.dispatch.call_args.kwargs["time_limit_s"] == 900

    def test_nonexistent_local_path_raises(self):
        m = self._setup_mixin()
        opts = EvaluationOptions()
        with pytest.raises(FileNotFoundError, match="Repository not found"):
            m.start_evaluation("/nonexistent/path", "/reports", opts)

    @patch("quodeq.services.evaluation_mixin.register_project")
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
        with patch("quodeq.services.evaluation_mixin.score_completed_evidence") as mock_score, \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"):
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

    def test_cancel_before_report_path_marker_does_not_raise(self):
        # A job cancelled in its first seconds has no output_project /
        # output_run_id yet (the report_path marker hasn't been parsed).
        # Building the run_dir path with None segments raised TypeError and
        # turned the cancel into an HTTP 500 after the process was already
        # killed.
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(job_id="j1", status="running")
        with patch("quodeq.services.evaluation_mixin.score_completed_evidence") as mock_score, \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status") as mock_wait:
            result = m.cancel_evaluation("j1", reports_dir="/reports")
        assert result is True
        mock_wait.assert_not_called()
        mock_score.assert_not_called()

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
             patch("quodeq.services.evaluation_mixin.score_completed_evidence") as mock_score, \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"):
            result = m.cancel_evaluation("ext-run-42", reports_dir="/reports")
        assert result is True
        mock_score.assert_called_once()
        # Scoring was passed the snapshot's project/run ids, proving it came
        # from get_evaluation_status (not the dead get_job path).
        call_args = mock_score.call_args
        assert call_args.args[0] == "/reports"
        assert call_args.args[1]["outputProject"] == "proj-uuid"
        assert call_args.args[1]["outputRunId"] == "run-42"


class TestWaitForTerminalStatus:
    def test_returns_true_when_status_already_terminal(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        (run_dir / "status.json").write_text(json.dumps({"state": "cancelled"}))
        assert _wait_for_terminal_status(run_dir, timeout_s=0.2) is True

    def test_recognizes_all_three_terminal_states(self, tmp_path: Path):
        for state in ("done", "failed", "cancelled"):
            run_dir = tmp_path / f"run-{state}"
            run_dir.mkdir()
            (run_dir / "status.json").write_text(json.dumps({"state": state}))
            assert _wait_for_terminal_status(run_dir, timeout_s=0.2) is True

    def test_returns_false_on_timeout_when_state_never_terminal(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        (run_dir / "status.json").write_text(json.dumps({"state": "running"}))
        assert _wait_for_terminal_status(
            run_dir, timeout_s=0.1, poll_interval_s=0.02,
        ) is False

    def test_returns_false_on_timeout_when_status_missing(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        # No status.json file at all -- expected during the brief window
        # before the lifecycle handler creates it.
        assert _wait_for_terminal_status(
            run_dir, timeout_s=0.1, poll_interval_s=0.02,
        ) is False

    def test_returns_false_on_malformed_status(self, tmp_path: Path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        (run_dir / "status.json").write_text("not valid json")
        assert _wait_for_terminal_status(
            run_dir, timeout_s=0.1, poll_interval_s=0.02,
        ) is False

    def test_polls_until_terminal_appears(self, tmp_path: Path):
        # Real-world scenario: status starts running, then the subprocess
        # lifecycle handler flushes terminal a moment later. We expect
        # _wait_for_terminal_status to bridge that gap.
        import threading
        import time as _time

        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        status_path = run_dir / "status.json"
        status_path.write_text(json.dumps({"state": "running"}))

        def write_terminal() -> None:
            _time.sleep(0.05)
            status_path.write_text(json.dumps({"state": "cancelled"}))

        threading.Thread(target=write_terminal, daemon=True).start()
        assert _wait_for_terminal_status(
            run_dir, timeout_s=budget(1.0), poll_interval_s=0.02,
        ) is True


class TestCancelEvaluationWaitsForTerminal:
    def test_cancel_calls_wait_for_terminal_status_after_cancel_job(self):
        # Regression: pre-fix, cancel_evaluation returned before status.json
        # was flushed to terminal, producing the "two running rows" UX
        # window after cancel-then-start.
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(
            job_id="j1", status="running",
            output_project="proj", output_run_id="run1",
        )
        with patch("quodeq.services.evaluation_mixin._wait_for_terminal_status") as mock_wait, \
             patch("quodeq.services.evaluation_mixin.score_completed_evidence"):
            m.cancel_evaluation("j1", reports_dir="/reports")
        mock_wait.assert_called_once()
        run_dir_arg = mock_wait.call_args.args[0]
        assert run_dir_arg == Path("/reports/proj/run1")

    def test_cancel_skips_wait_when_no_reports_dir(self):
        # When reports_dir is None there's no run_dir to watch; the wait
        # is part of the same conditional block that gates _score and
        # _discard, so it stays inert.
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(job_id="j1", status="running")
        with patch("quodeq.services.evaluation_mixin._wait_for_terminal_status") as mock_wait:
            m.cancel_evaluation("j1")
        mock_wait.assert_not_called()


class TestCancelDiscardPartial:
    def test_discard_default_off_does_not_clean(self):
        # Cancel without discard_partial=True must not touch any files.
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(
            job_id="j1", status="running",
            output_project="proj", output_run_id="run1",
        )
        with patch("quodeq.services.evaluation_mixin.score_completed_evidence"), \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"), \
             patch("quodeq.services.evaluation_mixin._discard_run_state") as mock_discard:
            m.cancel_evaluation("j1", reports_dir="/reports")
        mock_discard.assert_not_called()

    def test_discard_true_invokes_cleanup(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.cancel_job.return_value = True
        m._jobs.get_job.return_value = JobSnapshot(
            job_id="j1", status="running",
            output_project="proj", output_run_id="run1",
        )
        with patch("quodeq.services.evaluation_mixin.score_completed_evidence"), \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"), \
             patch("quodeq.services.evaluation_mixin._discard_run_state") as mock_discard:
            m.cancel_evaluation("j1", reports_dir="/reports", discard_partial=True)
        mock_discard.assert_called_once()
        args = mock_discard.call_args.args
        assert args[0] == "/reports"
        assert args[1]["outputProject"] == "proj"
        assert args[1]["outputRunId"] == "run1"


