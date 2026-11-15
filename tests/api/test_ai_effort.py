"""Tests for the reasoning-effort plumbing: Settings payload -> AI_EFFORT env ->
AnalysisConfig.ai_effort -> the provider's effort flag on the CLI command line,
plus its place in the analysis cache key."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.cache import model_id_from
from quodeq.analysis.runner import AnalysisOptions
from quodeq.analysis.subprocess import AnalysisConfig, build_ai_cmd, run_analysis
from quodeq.api.app import create_app
from quodeq.services.base import ActionProvider, EvaluationOptions
from quodeq.services.filesystem import FilesystemActionProvider


def _effort_args(provider: str, effort: str | None) -> list[str]:
    """The full command line build_ai_cmd makes for *provider* at *effort*."""
    args, _ = build_ai_cmd("p", AnalysisConfig(ai_cmd=provider, ai_model="m", ai_effort=effort))
    return args


class TestEffortOnTheCommandLine:
    def test_claude_gets_its_effort_flag(self) -> None:
        args = _effort_args("claude", "max")
        assert args[args.index("--effort") + 1] == "max"

    def test_codex_gets_its_reasoning_config(self) -> None:
        args = _effort_args("codex", "high")
        assert args[args.index("-c", args.index("m")) + 1] == 'model_reasoning_effort="high"'

    @pytest.mark.parametrize(("provider", "effort"), [
        ("claude", None), ("claude", "bogus"), ("codex", "bogus"), ("gemini", "high"),
    ])
    def test_unset_unlisted_or_unsupported_passes_nothing(self, provider: str, effort: str | None) -> None:
        # An unlisted level logs a warning (headless AI_EFFORT) and falls back.
        args = _effort_args(provider, effort)
        assert "--effort" not in args
        assert not any("model_reasoning_effort" in a for a in args)


def test_env_effort_reaches_the_spawned_cli(tmp_path: Path, installed_cli) -> None:
    stream_file = tmp_path / "stream.json"
    stream_file.touch()
    process = MagicMock(returncode=0)
    process.poll.return_value = 0
    process.wait.return_value = 0
    with patch("quodeq.analysis._process.subprocess.Popen", return_value=process) as popen:
        try:
            run_analysis(
                work_dir=tmp_path, prompt="p", stream_file=stream_file,
                config=AnalysisConfig(ai_cmd="claude", ai_model="opus"),
                env={"AI_EFFORT": "high"},
            )
        except (OSError, RuntimeError, ValueError, TypeError):
            pass  # Intentional: only the captured Popen args matter here
    args = popen.call_args[0][0]
    assert args[args.index("--effort") + 1] == "high"


class TestEffortInCacheKey:
    def test_effort_suffixes_the_model_id(self) -> None:
        rc = SimpleNamespace(options=AnalysisOptions(ai_model="opus", ai_effort="high"))
        assert model_id_from(rc) == "opus@high"

    def test_default_effort_keeps_existing_keys(self) -> None:
        rc = SimpleNamespace(options=AnalysisOptions(ai_model="opus"))
        assert model_id_from(rc) == "opus"


def test_effort_exported_to_the_run_env(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    captured: dict = {}

    class StubJobs:
        def start_job(self, cmd, launch=None):
            captured["env"] = launch.env
            return {"jobId": "test"}

    FilesystemActionProvider(job_manager=StubJobs()).start_evaluation(
        repo=str(repo), reports_dir=str(tmp_path / "reports"),
        options=EvaluationOptions(ai_effort="high"),
    )
    assert captured["env"]["AI_EFFORT"] == "high"


class _CapturingProvider(ActionProvider):
    def __init__(self, captured: dict) -> None:
        self.captured = captured

    def start_evaluation(self, repo, reports_dir, options: EvaluationOptions):
        self.captured["options"] = options
        return {"jobId": "j1", "status": "running", "logs": []}

    def __getattr__(self, name):  # every other ActionProvider call is unused here
        return lambda *a, **k: {}


class TestEvaluateRoute:
    def _post(self, tmp_path: Path, body: dict) -> tuple[int, dict, dict]:
        captured: dict = {}
        client = create_app(_CapturingProvider(captured)).test_client()
        with patch("pathlib.Path.home", new=classmethod(lambda cls: tmp_path)):
            response = client.post(
                "/api/evaluations", json={"repo": str(tmp_path), **body},
                headers={"Origin": "http://localhost"},
            )
        return response.status_code, captured, response.get_json()

    def test_listed_effort_reaches_the_options(self, tmp_path: Path) -> None:
        status, captured, _ = self._post(tmp_path, {"aiCmd": "claude", "aiEffort": "xhigh"})
        assert status == HTTPStatus.ACCEPTED
        assert captured["options"].ai_effort == "xhigh"

    @pytest.mark.parametrize(("provider", "effort"), [("codex", "bogus"), ("gemini", "high")])
    def test_effort_the_provider_lacks_is_rejected_without_echo(self, tmp_path: Path, provider: str, effort: str) -> None:
        status, captured, body = self._post(tmp_path, {"aiCmd": provider, "aiEffort": effort})
        assert status == HTTPStatus.BAD_REQUEST
        assert effort not in body["error"]
        assert "options" not in captured

    def test_rejection_lists_the_accepted_levels(self, tmp_path: Path) -> None:
        _, _, body = self._post(tmp_path, {"aiCmd": "codex", "aiEffort": "bogus"})
        assert body["error"] == "Unsupported effort. This provider accepts: low, medium, high, xhigh, max, ultra."
