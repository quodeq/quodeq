"""End-to-end behavioural tests: verify the selected model actually reaches
the CLI subprocess args that would be passed to the AI.

These tests patch subprocess.Popen (no real AI calls) and assert that
``--model <expected>`` appears in the command line, proving the full chain:

    PowerSelector level → subagentModel payload → SUBAGENT_MODEL env /
    AnalysisOptions.subagent_model → AnalysisConfig.ai_model →
    build_ai_cmd() → subprocess.Popen args
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig, run_analysis

# Model name constants used across test methods.
_MODEL_HAIKU = "claude-haiku-4-5"
_MODEL_SONNET = "claude-sonnet-4-6"
_MODEL_OPUS = "claude-opus-4-6"


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

    with patch("quodeq.analysis._process.subprocess.Popen", return_value=mock_process) as mock_popen:
        try:
            run_analysis(
                work_dir=tmp_path,
                prompt="test prompt",
                stream_file=stream_file,
                config=config,
            )
        except (OSError, RuntimeError, ValueError, TypeError):
            pass  # Intentional: run_analysis may fail after Popen (missing files, mock side-effects); we only inspect the captured Popen args

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

    @pytest.mark.parametrize("configured", [_MODEL_HAIKU, _MODEL_SONNET, _MODEL_OPUS])
    def test_configured_model_reaches_cli(self, tmp_path: Path, configured: str) -> None:
        args = _capture_popen_args(tmp_path, configured)
        assert _extract_model_from_args(args) == configured

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

    @pytest.mark.parametrize(
        ("model", "files", "dimension"),
        [
            (_MODEL_OPUS, ["a.py", "b.py"], "security"),
            (_MODEL_HAIKU, ["x.py"], "perf"),
        ],
    )
    def test_pool_agents_inherit_model(
        self, tmp_path: Path, model: str, files: list[str], dimension: str,
    ) -> None:
        from quodeq.analysis.subagents.file_queue import FileQueue
        from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool

        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, files)

        base = AnalysisConfig(ai_model=model)
        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=len(files), prompt="test", dimension=dimension),
            config=base,
        )

        for idx in range(len(files)):
            ac, _, _ = pool._build_agent_config(idx)
            assert ac.ai_model == model, (
                f"agent-{idx} got ai_model={ac.ai_model!r}, expected {model!r}"
            )


# ---------------------------------------------------------------------------
# Tests: Runner model resolution (full chain)
# ---------------------------------------------------------------------------

class TestRunnerModelResolution:
    """The runner builds AnalysisConfig.ai_model from options → env → default."""

    def _resolve(self, subagent_model: str | None = None, env_model: str | None = None) -> str:
        """Exercise the model-resolution precedence by calling the real
        ``_pool_launcher._build_pool_config`` production function, so a
        regression at its ``config.options.subagent_model or
        default_subagent_model(env) or config.options.ai_model`` line fails
        these tests. ``ai_model`` is set to the haiku constant here to stand
        in for whatever default the caller configured, since AnalysisOptions
        itself has no built-in default.
        """
        from quodeq.analysis.runner import AnalysisOptions, RunConfig
        from quodeq.analysis.subagents._pool_launcher import LaunchPoolParams, _build_pool_config

        config = RunConfig(
            src=Path("."), language="python",
            options=AnalysisOptions(subagent_model=subagent_model, ai_model=_MODEL_HAIKU),
        )
        params = LaunchPoolParams(evidence_dir=Path("."), queue_path=Path("queue.json"), prompt="p")
        env = {"SUBAGENT_MODEL": env_model} if env_model else {}
        built = _build_pool_config(config, "test-dim", params, time_limit=60, env=env)
        return built.ai_model

    @pytest.mark.parametrize("requested", [_MODEL_HAIKU, _MODEL_SONNET, _MODEL_OPUS])
    def test_requested_model_wins(self, requested: str) -> None:
        assert self._resolve(requested) == requested

    def test_env_fallback_when_no_option(self) -> None:
        assert self._resolve(None, _MODEL_SONNET) == _MODEL_SONNET

    def test_default_is_haiku_when_nothing_set(self) -> None:
        assert self._resolve(None, None) == _MODEL_HAIKU

    def test_option_overrides_env(self) -> None:
        assert self._resolve(_MODEL_OPUS, _MODEL_HAIKU) == _MODEL_OPUS


# ---------------------------------------------------------------------------
# Tests: API → env var → subprocess (integration)
# ---------------------------------------------------------------------------

class _StubJobManager:
    """Captures the env dict passed to start_job for assertion."""

    def __init__(self):
        self.captured_env: dict = {}

    def start_job(self, cmd, launch=None):
        self.captured_env = launch.env
        return {"jobId": "test"}


@pytest.fixture()
def filesystem_provider_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Return a (repo_path, reports_dir, stub_job_manager, provider) tuple.

    The model env vars are cleared first: ``build_eval_env`` starts from
    ``os.environ`` when no env is passed, so a developer (or CI runner) with
    ``SUBAGENT_MODEL`` exported would see it in ``captured_env`` and the
    no-model case would fail for a reason that has nothing to do with the
    chain under test.
    """
    from quodeq.services.filesystem import FilesystemActionProvider

    monkeypatch.delenv("SUBAGENT_MODEL", raising=False)
    monkeypatch.delenv("QUODEQ_SUBAGENT_MODEL", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    stub = _StubJobManager()
    provider = FilesystemActionProvider(job_manager=stub)
    return repo, tmp_path / "reports", stub, provider


class TestApiToSubprocessIntegration:
    """POST /api/evaluations with subagentModel should set SUBAGENT_MODEL
    in the env passed to the subprocess."""

    @pytest.mark.parametrize("requested", [_MODEL_SONNET, _MODEL_OPUS])
    def test_full_chain_sets_subagent_model(self, filesystem_provider_stub, requested: str) -> None:
        from quodeq.services.base import EvaluationOptions

        repo, reports_dir, stub, provider = filesystem_provider_stub
        provider.start_evaluation(
            repo=str(repo),
            reports_dir=str(reports_dir),
            options=EvaluationOptions(subagent_model=requested),
        )
        assert stub.captured_env["SUBAGENT_MODEL"] == requested

    def test_full_chain_no_model_no_env_key(self, filesystem_provider_stub) -> None:
        from quodeq.services.base import EvaluationOptions

        repo, reports_dir, stub, provider = filesystem_provider_stub
        provider.start_evaluation(
            repo=str(repo),
            reports_dir=str(reports_dir),
            options=EvaluationOptions(),
        )
        assert "SUBAGENT_MODEL" not in stub.captured_env
