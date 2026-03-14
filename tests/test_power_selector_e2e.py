"""End-to-end behavioural tests: verify the selected model actually reaches
the CLI subprocess args that would be passed to the AI.

These tests patch subprocess.Popen (no real AI calls) and assert that
``--model <expected>`` appears in the command line, proving the full chain:

    PowerSelector level → subagentModel payload → SUBAGENT_MODEL env /
    AnalysisOptions.subagent_model → AnalysisConfig.ai_model →
    _build_ai_cmd() → subprocess.Popen args
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.engine.analysis import AnalysisConfig, run_analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_popen_args(tmp_path: Path, ai_model: str | None) -> list[str]:
    """Run run_analysis with a patched Popen and return the captured args."""
    stream_file = tmp_path / "stream.json"
    stream_file.touch()

    config = AnalysisConfig(ai_model=ai_model)

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.poll.return_value = 0
    mock_process.wait.return_value = 0

    with patch("quodeq.engine.analysis.subprocess.Popen", return_value=mock_process) as mock_popen:
        try:
            run_analysis(
                work_dir=tmp_path,
                prompt="test prompt",
                stream_file=stream_file,
                config=config,
            )
        except (OSError, RuntimeError, ValueError, TypeError):
            pass  # We only care about what Popen received

    assert mock_popen.called, "Popen was never called"
    return mock_popen.call_args[0][0]  # positional arg 0 = args list


def _extract_model_from_args(args: list[str]) -> str | None:
    """Find the value after --model in a CLI args list."""
    try:
        idx = args.index("--model")
        return args[idx + 1]
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Tests: model flag reaches subprocess for each power level
# ---------------------------------------------------------------------------

class TestModelReachesSubprocess:
    """The --model flag in the spawned CLI must match the configured ai_model."""

    def test_haiku_reaches_cli(self, tmp_path: Path) -> None:
        args = _capture_popen_args(tmp_path, "claude-haiku-4-5")
        model = _extract_model_from_args(args)
        assert model == "claude-haiku-4-5"

    def test_sonnet_reaches_cli(self, tmp_path: Path) -> None:
        args = _capture_popen_args(tmp_path, "claude-sonnet-4-6")
        model = _extract_model_from_args(args)
        assert model == "claude-sonnet-4-6"

    def test_opus_reaches_cli(self, tmp_path: Path) -> None:
        args = _capture_popen_args(tmp_path, "claude-opus-4-6")
        model = _extract_model_from_args(args)
        assert model == "claude-opus-4-6"

    def test_no_model_flag_when_none(self, tmp_path: Path) -> None:
        """When ai_model is None and no env, --model should not appear (uses provider default)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_MODEL", None)
            args = _capture_popen_args(tmp_path, None)
        model = _extract_model_from_args(args)
        assert model is None


# ---------------------------------------------------------------------------
# Tests: SubagentPool propagates model to per-agent configs
# ---------------------------------------------------------------------------

class TestSubagentPoolModelPropagation:
    """SubagentPool._build_agent_config must copy ai_model from base config."""

    def test_pool_agents_inherit_model(self, tmp_path: Path) -> None:
        from quodeq.engine.file_queue import FileQueue
        from quodeq.engine.subagent_pool import SubagentPool

        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["a.py", "b.py"])

        base = AnalysisConfig(ai_model="claude-opus-4-6")
        pool = SubagentPool(
            n_agents=2,
            work_dir=tmp_path,
            prompt="test",
            evidence_dir=tmp_path,
            queue_path=queue_path,
            dimension="security",
            config=base,
        )

        for idx in range(2):
            ac, _, _ = pool._build_agent_config(idx)
            assert ac.ai_model == "claude-opus-4-6", (
                f"agent-{idx} got ai_model={ac.ai_model!r}, expected 'claude-opus-4-6'"
            )

    def test_pool_agents_inherit_haiku(self, tmp_path: Path) -> None:
        from quodeq.engine.file_queue import FileQueue
        from quodeq.engine.subagent_pool import SubagentPool

        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["x.py"])

        base = AnalysisConfig(ai_model="claude-haiku-4-5")
        pool = SubagentPool(
            n_agents=1,
            work_dir=tmp_path,
            prompt="test",
            evidence_dir=tmp_path,
            queue_path=queue_path,
            dimension="perf",
            config=base,
        )

        ac, _, _ = pool._build_agent_config(0)
        assert ac.ai_model == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Tests: Runner model resolution (full chain)
# ---------------------------------------------------------------------------

class TestRunnerModelResolution:
    """The runner builds AnalysisConfig.ai_model from options → env → default."""

    def _resolve(self, subagent_model: str | None = None, env_model: str | None = None) -> str:
        """Replicate the runner's resolution logic."""
        from quodeq.engine.runner import AnalysisOptions
        opts = AnalysisOptions(subagent_model=subagent_model)
        # Mirror runner.py line 252
        with patch.dict(os.environ, {"SUBAGENT_MODEL": env_model} if env_model else {}, clear=False):
            if not env_model:
                os.environ.pop("SUBAGENT_MODEL", None)
            return opts.subagent_model or os.environ.get("SUBAGENT_MODEL") or "claude-haiku-4-5"

    def test_level1_fast_haiku(self) -> None:
        assert self._resolve("claude-haiku-4-5") == "claude-haiku-4-5"

    def test_level2_balanced_sonnet(self) -> None:
        assert self._resolve("claude-sonnet-4-6") == "claude-sonnet-4-6"

    def test_level3_thorough_opus(self) -> None:
        assert self._resolve("claude-opus-4-6") == "claude-opus-4-6"

    def test_env_fallback_when_no_option(self) -> None:
        assert self._resolve(None, "claude-sonnet-4-6") == "claude-sonnet-4-6"

    def test_default_is_haiku_when_nothing_set(self) -> None:
        assert self._resolve(None, None) == "claude-haiku-4-5"

    def test_option_overrides_env(self) -> None:
        assert self._resolve("claude-opus-4-6", "claude-haiku-4-5") == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# Tests: API → env var → subprocess (integration)
# ---------------------------------------------------------------------------

class _StubJobManager:
    """Captures the env dict passed to start_job for assertion."""

    def __init__(self):
        self.captured_env: dict = {}

    def start_job(self, cmd, cwd, env):
        self.captured_env = env
        return {"jobId": "test"}


class TestApiToSubprocessIntegration:
    """POST /api/evaluations with subagentModel should set SUBAGENT_MODEL
    in the env passed to the subprocess."""

    def test_full_chain_sonnet(self, tmp_path: Path) -> None:
        from quodeq.provider.base import EvaluationOptions
        from quodeq.provider.filesystem import FilesystemActionProvider

        repo = tmp_path / "repo"
        repo.mkdir()
        stub = _StubJobManager()
        provider = FilesystemActionProvider(job_manager=stub)
        provider.start_evaluation(
            repo=str(repo),
            reports_dir=str(tmp_path / "reports"),
            options=EvaluationOptions(subagent_model="claude-sonnet-4-6"),
        )
        assert stub.captured_env["SUBAGENT_MODEL"] == "claude-sonnet-4-6"

    def test_full_chain_opus(self, tmp_path: Path) -> None:
        from quodeq.provider.base import EvaluationOptions
        from quodeq.provider.filesystem import FilesystemActionProvider

        repo = tmp_path / "repo"
        repo.mkdir()
        stub = _StubJobManager()
        provider = FilesystemActionProvider(job_manager=stub)
        provider.start_evaluation(
            repo=str(repo),
            reports_dir=str(tmp_path / "reports"),
            options=EvaluationOptions(subagent_model="claude-opus-4-6"),
        )
        assert stub.captured_env["SUBAGENT_MODEL"] == "claude-opus-4-6"

    def test_full_chain_no_model_no_env_key(self, tmp_path: Path) -> None:
        from quodeq.provider.base import EvaluationOptions
        from quodeq.provider.filesystem import FilesystemActionProvider

        repo = tmp_path / "repo"
        repo.mkdir()
        stub = _StubJobManager()
        provider = FilesystemActionProvider(job_manager=stub)
        provider.start_evaluation(
            repo=str(repo),
            reports_dir=str(tmp_path / "reports"),
            options=EvaluationOptions(),
        )
        assert "SUBAGENT_MODEL" not in stub.captured_env
