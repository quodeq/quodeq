"""Tests for evaluation_mixin.py — _build_evaluate_cmd/_build_eval_env/dispatcher.

Split from test_evaluation_mixin.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from quodeq.core.types import JobSnapshot
from quodeq.services.base import (
    DEFAULT_MAX_SUBAGENTS,
    DEFAULT_TIME_LIMIT,
    EvaluationOptions,
)
from quodeq.services.evaluation_mixin import (
    FsEvaluationMixin,
    SubprocessDispatcher,
    _build_evaluate_cmd,
)


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
        opts = EvaluationOptions(max_subagents=DEFAULT_MAX_SUBAGENTS)
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

    def test_ai_cmd_path_exported(self):
        m = self._mixin()
        opts = EvaluationOptions(ai_cmd="claude", ai_cmd_path="/opt/bin/claude-api")
        env = m._build_eval_env("/repo", opts, env={})
        assert env["AI_CMD_PATH"] == "/opt/bin/claude-api"

    def test_no_ai_cmd_path_not_exported(self):
        m = self._mixin()
        env = m._build_eval_env("/repo", EvaluationOptions(ai_cmd="claude"), env={})
        assert "AI_CMD_PATH" not in env

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
        opts = EvaluationOptions(time_limit=DEFAULT_TIME_LIMIT)
        env = m._build_eval_env("/repo", opts, env={})
        assert env["QUODEQ_TIME_LIMIT"] == str(DEFAULT_TIME_LIMIT)

    def test_unlimited_time_limit_propagated_as_zero(self):
        # 0 means "unlimited". It must reach the subprocess explicitly:
        # with the env var absent the CLI resolves the limit to None and
        # the pool substitutes the 600s default, so "unlimited" runs died
        # at exactly 10 minutes. Downstream treats 0 as unlimited and
        # sets no deadline.
        m = self._mixin()
        opts = EvaluationOptions(time_limit=0)
        env = m._build_eval_env("/repo", opts, env={})
        assert env["QUODEQ_TIME_LIMIT"] == "0"

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

    def test_cloud_provider_api_key_exported(self):
        # The subprocess resolves cloud keys from the env var named by the
        # provider's api_key_env. Only omlx used to get its key exported, so
        # an OpenRouter key typed in Settings was silently discarded.
        m = self._mixin()
        opts = EvaluationOptions(ai_cmd="openrouter", provider_api_key="sk-or-1")
        env = m._build_eval_env("/repo", opts, env={})
        assert env["OPENROUTER_API_KEY"] == "sk-or-1"

    def test_omlx_key_and_base_still_exported(self):
        m = self._mixin()
        opts = EvaluationOptions(
            ai_cmd="omlx", provider_api_key="k1", provider_api_base="http://h:1/v1",
        )
        env = m._build_eval_env("/repo", opts, env={})
        assert env["OMLX_API_KEY"] == "k1"
        assert env["OMLX_BASE_URL"] == "http://h:1/v1"

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
            time_limit_s=None,
        )

    def test_forwards_time_limit(self):
        mock_mgr = MagicMock()
        mock_mgr.start_job.return_value = JobSnapshot(job_id="j1", status="running")
        dispatcher = SubprocessDispatcher(mock_mgr)
        dispatcher.dispatch(["cmd"], time_limit_s=0)
        assert mock_mgr.start_job.call_args.kwargs["time_limit_s"] == 0


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

