"""Tests for evaluation_mixin.py — command building, env building, dispatch, scoring."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from quodeq.core.types import JobSnapshot
from quodeq.services.base import EvaluationOptions, _DEFAULT_MAX_SUBAGENTS, _DEFAULT_TIME_LIMIT
from quodeq.services.evaluation_mixin import (
    FsEvaluationMixin,
    SubprocessDispatcher,
    _build_evaluate_cmd,
    _discard_run_state,
    _read_project_source_file_count,
    _read_queue_files_count,
    _register_project,
    _score_completed_evidence,
    _wait_for_terminal_status,
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

    def test_subprocess_cmd_emits_clean_scan_flag(self, tmp_path: Path):
        """When clean_scan is True, the spawned CLI gets --clean-scan."""
        opts = EvaluationOptions(clean_scan=True, dimensions="security")
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path / "reports"))
        assert "--clean-scan" in cmd
        assert "--incremental" not in cmd

    def test_subprocess_cmd_omits_clean_scan_by_default(self, tmp_path: Path):
        """When clean_scan is False (default), --clean-scan is not emitted."""
        opts = EvaluationOptions(dimensions="security")
        cmd = _build_evaluate_cmd(str(tmp_path), opts, str(tmp_path / "reports"))
        assert "--clean-scan" not in cmd
        assert "--incremental" not in cmd


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

    def test_custom_time_limit(self):
        m = self._mixin()
        opts = EvaluationOptions(time_limit=1200)
        env = m._build_eval_env("/repo", opts, env={})
        assert env["QUODEQ_TIME_LIMIT"] == "1200"

    def test_default_time_limit_is_set(self):
        # Regression: previously this env var was only injected when the
        # value differed from the default. Dashboard runs that kept the
        # default 10-min budget got no env var, so the CLI subprocess
        # couldn't resolve a time limit, the analyzing_start marker never
        # fired, and the UI countdown timer froze at the static budget.
        m = self._mixin()
        opts = EvaluationOptions(time_limit=_DEFAULT_TIME_LIMIT)
        env = m._build_eval_env("/repo", opts, env={})
        assert env["QUODEQ_TIME_LIMIT"] == str(_DEFAULT_TIME_LIMIT)

    def test_unlimited_time_limit_not_set(self):
        # 0 means "unlimited" — no deadline should be propagated.
        m = self._mixin()
        opts = EvaluationOptions(time_limit=0)
        env = m._build_eval_env("/repo", opts, env={})
        assert "QUODEQ_TIME_LIMIT" not in env

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
        mock_mgr.start_job.assert_called_once_with(
            ["cmd"], cwd="/tmp", env={"A": "1"}, ai_provider=None, ai_model=None,
        )


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

    def test_url_input_rejected(self):
        """Clone-on-add (A4): start_evaluation refuses URLs; clone happens at registration."""
        m = self._setup_mixin()
        opts = EvaluationOptions()
        with pytest.raises(ValueError, match="not supported"):
            m.start_evaluation("https://github.com/org/repo.git", "/reports", opts)
        m._dispatcher.dispatch.assert_not_called()

    @patch("quodeq.services.evaluation_mixin._register_project")
    def test_start_with_local_dir(self, mock_reg, tmp_path: Path):
        m = self._setup_mixin()
        opts = EvaluationOptions()
        snap = m.start_evaluation(str(tmp_path), str(tmp_path / "reports"), opts)
        assert snap.job_id == "j1"

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
        with patch("quodeq.services.evaluation_mixin._score_completed_evidence") as mock_score, \
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
             patch("quodeq.services.evaluation_mixin._score_completed_evidence") as mock_score, \
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
            run_dir, timeout_s=1.0, poll_interval_s=0.02,
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
             patch("quodeq.services.evaluation_mixin._score_completed_evidence"):
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
        with patch("quodeq.services.evaluation_mixin._score_completed_evidence"), \
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
        with patch("quodeq.services.evaluation_mixin._score_completed_evidence"), \
             patch("quodeq.services.evaluation_mixin._wait_for_terminal_status"), \
             patch("quodeq.services.evaluation_mixin._discard_run_state") as mock_discard:
            m.cancel_evaluation("j1", reports_dir="/reports", discard_partial=True)
        mock_discard.assert_called_once()
        args = mock_discard.call_args.args
        assert args[0] == "/reports"
        assert args[1]["outputProject"] == "proj"
        assert args[1]["outputRunId"] == "run1"


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
# _read_queue_files_count + _read_project_source_file_count
# ---------------------------------------------------------------------------

class TestReadQueueFilesCount:
    """Pin the contract that salvage scoring uses to populate `files_read`.

    Without this, ``_score_completed_evidence`` writes evals with
    ``filesRead: 0`` — which the ``scoring_view`` trust rule rejects as
    untrustworthy stubs, falling the user back to an older run's stale
    score for that dim despite real findings being on disk.
    """

    def test_sums_files_across_taken_batches(self, tmp_path: Path):
        # Real-shape queue: each batch is `{files, agent, ts}`; files_read
        # is the count of files dispatched across all batches.
        queue = tmp_path / "q.json"
        queue.write_text(json.dumps({
            "taken": [
                {"files": ["a.py", "b.py", "c.py"], "agent": "a1", "ts": 1},
                {"files": ["d.py", "e.py"], "agent": "a2", "ts": 2},
            ],
            "pending": [],
        }))
        assert _read_queue_files_count(queue) == 5

    def test_zero_when_no_taken_entries(self, tmp_path: Path):
        queue = tmp_path / "q.json"
        queue.write_text(json.dumps({"taken": [], "pending": ["x.py"]}))
        assert _read_queue_files_count(queue) == 0

    def test_zero_when_missing_file(self, tmp_path: Path):
        # Salvage path encounters a non-existent queue (rare but possible
        # if a dim never reached the queue-creation step) — must not raise.
        assert _read_queue_files_count(tmp_path / "missing.json") == 0

    def test_zero_when_corrupt_json(self, tmp_path: Path):
        queue = tmp_path / "q.json"
        queue.write_text("{not json")
        assert _read_queue_files_count(queue) == 0

    def test_handles_missing_files_field_in_batch(self, tmp_path: Path):
        # Defensive: a malformed batch missing `files` shouldn't crash.
        queue = tmp_path / "q.json"
        queue.write_text(json.dumps({
            "taken": [{"agent": "a1", "ts": 1}, {"files": ["x.py"]}],
            "pending": [],
        }))
        assert _read_queue_files_count(queue) == 1


class TestReadProjectSourceFileCount:
    def test_reads_from_scan_json(self, tmp_path: Path):
        proj_dir = tmp_path / "reports" / "proj"
        proj_dir.mkdir(parents=True)
        (proj_dir / "scan.json").write_text(json.dumps({"total_files": 1855}))
        assert _read_project_source_file_count(str(tmp_path / "reports"), "proj") == 1855

    def test_zero_when_scan_missing(self, tmp_path: Path):
        assert _read_project_source_file_count(str(tmp_path), "ghost") == 0

    def test_zero_when_corrupt_scan(self, tmp_path: Path):
        proj_dir = tmp_path / "reports" / "proj"
        proj_dir.mkdir(parents=True)
        (proj_dir / "scan.json").write_text("{nope")
        assert _read_project_source_file_count(str(tmp_path / "reports"), "proj") == 0

    def test_zero_when_total_files_not_int(self, tmp_path: Path):
        proj_dir = tmp_path / "reports" / "proj"
        proj_dir.mkdir(parents=True)
        (proj_dir / "scan.json").write_text(json.dumps({"total_files": "many"}))
        assert _read_project_source_file_count(str(tmp_path / "reports"), "proj") == 0


class TestScoreCompletedEvidencePopulatesCoverage:
    """The bug this fixes: salvage-written evals had filesRead=0, so the
    scoring_view trust rule (filesRead > 0) rejected them as stubs. The
    user-visible symptom was a real, fully-completed dim's score being
    silently replaced by an older run's score on the overview cards.
    """

    def test_files_read_populated_from_queue(self, tmp_path: Path):
        reports = tmp_path / "reports"
        proj = reports / "proj"
        run = proj / "run1"
        ev_dir = run / "evidence"
        ev_dir.mkdir(parents=True)
        # Mark the project's scan with a real total_files.
        (proj / "scan.json").write_text(json.dumps({"total_files": 1000}))
        # 7 files dispatched across two agent batches.
        (ev_dir / "security_queue.json").write_text(json.dumps({
            "taken": [
                {"files": ["a.py", "b.py", "c.py", "d.py"], "agent": "a1", "ts": 1},
                {"files": ["e.py", "f.py", "g.py"], "agent": "a2", "ts": 2},
            ],
            "pending": [],
        }))
        # Real findings written to JSONL (would normally come from agents).
        (ev_dir / "security_evidence.jsonl").write_text(
            '{"req": "S-CON-1", "t": "violation", "file": "a.py", "line": 1, "severity": "minor", "w": "x", "reason": "y"}\n'
        )

        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })

        eval_path = run / "evaluation" / "security.json"
        assert eval_path.is_file()
        eval_data = json.loads(eval_path.read_text())
        # The fix: filesRead reflects the queue's taken count, not 0.
        assert eval_data["filesRead"] == 7
        # And source_file_count comes from scan.json.
        assert eval_data["sourceFileCount"] == 1000

    def test_files_read_zero_when_no_queue(self, tmp_path: Path):
        # Edge case: if the queue file is missing entirely (which already
        # short-circuits the dim earlier in the function), the helper
        # gracefully returns 0 without crashing the broader walk.
        reports = tmp_path / "reports"
        ev_dir = reports / "proj" / "run1" / "evidence"
        ev_dir.mkdir(parents=True)
        # No queue file — _score_completed_evidence skips this dim entirely.
        (ev_dir / "security_evidence.jsonl").write_text('{"f":1}\n')
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })
        eval_path = reports / "proj" / "run1" / "evaluation" / "security.json"
        assert not eval_path.exists()  # skipped because no queue


# ---------------------------------------------------------------------------
# list_evaluations
# ---------------------------------------------------------------------------


class TestListEvaluations:
    def test_delegates_to_job_manager(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.list_jobs.return_value = []
        assert m.list_evaluations() == []


def test_evaluation_options_clean_scan_field_defaults_false():
    """User-facing flag: clean_scan opts OUT of cache; default behaviour is incremental."""
    from quodeq.services.base import EvaluationOptions
    opts = EvaluationOptions()
    assert opts.clean_scan is False
    assert not hasattr(opts, "incremental"), (
        "Old field name leaked through; rename incomplete."
    )
