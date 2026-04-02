"""Tests for the power-selector (subagent_model) plumbing across the backend stack."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.provider.base import EvaluationOptions
from quodeq.analysis.runner import AnalysisOptions

_MODEL_HAIKU = "claude-haiku-4-5"
_MODEL_OPUS = "claude-opus-4-6"
_MODEL_SONNET = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# EvaluationOptions — subagent_model field
# ---------------------------------------------------------------------------

class TestEvaluationOptionsSubagentModel:
    def test_default_is_none(self) -> None:
        opts = EvaluationOptions()
        assert opts.subagent_model is None

    def test_accepts_haiku(self) -> None:
        opts = EvaluationOptions(subagent_model=_MODEL_HAIKU)
        assert opts.subagent_model == _MODEL_HAIKU

    def test_accepts_sonnet(self) -> None:
        opts = EvaluationOptions(subagent_model=_MODEL_SONNET)
        assert opts.subagent_model == _MODEL_SONNET

    def test_accepts_opus(self) -> None:
        opts = EvaluationOptions(subagent_model=_MODEL_OPUS)
        assert opts.subagent_model == _MODEL_OPUS


# ---------------------------------------------------------------------------
# AnalysisOptions — subagent_model field
# ---------------------------------------------------------------------------

class TestAnalysisOptionsSubagentModel:
    def test_default_is_none(self) -> None:
        opts = AnalysisOptions()
        assert opts.subagent_model is None

    def test_stores_value(self) -> None:
        opts = AnalysisOptions(subagent_model=_MODEL_SONNET)
        assert opts.subagent_model == _MODEL_SONNET


# ---------------------------------------------------------------------------
# Evaluation mixin — SUBAGENT_MODEL env var
# ---------------------------------------------------------------------------

class TestEvaluationMixinSubagentModel:
    """start_evaluation should set SUBAGENT_MODEL in the subprocess env."""

    def _make_provider(self, captured: dict):
        from quodeq.provider.filesystem import FilesystemActionProvider

        class StubJobs:
            def start_job(self, cmd, cwd, env):
                captured["cmd"] = cmd
                captured["env"] = env
                return {"jobId": "test"}

        return FilesystemActionProvider(job_manager=StubJobs())

    def test_subagent_model_set_in_env(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        captured = {}
        provider = self._make_provider(captured)
        provider.start_evaluation(
            repo=str(repo),
            reports_dir=str(tmp_path / "reports"),
            options=EvaluationOptions(subagent_model=_MODEL_OPUS),
        )
        assert captured["env"]["SUBAGENT_MODEL"] == _MODEL_OPUS

    def test_subagent_model_not_in_env_when_none(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        captured = {}
        provider = self._make_provider(captured)
        provider.start_evaluation(
            repo=str(repo),
            reports_dir=str(tmp_path / "reports"),
            options=EvaluationOptions(),
        )
        assert "SUBAGENT_MODEL" not in captured["env"]

    def test_subagent_model_haiku_in_env(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        captured = {}
        provider = self._make_provider(captured)
        provider.start_evaluation(
            repo=str(repo),
            reports_dir=str(tmp_path / "reports"),
            options=EvaluationOptions(subagent_model=_MODEL_HAIKU),
        )
        assert captured["env"]["SUBAGENT_MODEL"] == _MODEL_HAIKU


# ---------------------------------------------------------------------------
# API route — subagentModel in JSON payload
# ---------------------------------------------------------------------------

class TestApiRouteSubagentModel:
    def _make_capturing_provider(self, captured: dict):
        from quodeq.provider.base import ActionProvider

        class CapturingProvider(ActionProvider):
            def list_projects(self, reports_dir):
                return {"projects": []}

            def get_dashboard(self, reports_dir, project, run):
                return {}

            def get_accumulated(self, reports_dir, project, as_of):
                return {}

            def get_dimension_eval(self, reports_dir, project, run_id, dimension):
                return {}

            def get_run_plan(self, reports_dir, project, run_id):
                return {}

            def get_violations(self, reports_dir, project, run_id):
                return {}

            def start_evaluation(self, repo, reports_dir, options: EvaluationOptions):
                captured["options"] = options
                return {"jobId": "j1", "status": "running", "logs": []}

            def get_evaluation_status(self, job_id):
                return None

            def browse_repo(self, path):
                return {"current": "/tmp", "parent": "/", "directories": [], "isGitRepo": False}

        return CapturingProvider()

    def test_subagent_model_forwarded_from_payload(self, tmp_path: Path) -> None:
        from quodeq.api.app import create_app

        captured = {}
        app = create_app(self._make_capturing_provider(captured))
        client = app.test_client()

        response = client.post("/api/evaluations", json={
            "repo": str(tmp_path),
            "subagentModel": _MODEL_SONNET,
        }, headers={"Origin": "http://localhost"})
        assert response.status_code == 202
        assert captured.get("options") is not None
        assert captured["options"].subagent_model == _MODEL_SONNET

    def test_subagent_model_none_when_not_provided(self, tmp_path: Path) -> None:
        from quodeq.api.app import create_app

        captured = {}
        app = create_app(self._make_capturing_provider(captured))
        client = app.test_client()

        response = client.post("/api/evaluations", json={
            "repo": str(tmp_path),
        }, headers={"Origin": "http://localhost"})
        assert captured.get("options") is not None
        assert captured["options"].subagent_model is None


# ---------------------------------------------------------------------------
# Runner — subagent model resolution (options > env > default)
# ---------------------------------------------------------------------------

class TestRunnerSubagentModelResolution:
    """The runner should pick subagent_model from options first, then
    QUODEQ_SUBAGENT_MODEL env, then fall back to None (client default)."""

    @staticmethod
    def _resolve(opts: AnalysisOptions) -> str | None:
        """Mirror the production resolution path in _subagent_runner."""
        from quodeq.analysis.subagents.runner import _default_subagent_model
        return opts.subagent_model or _default_subagent_model()

    def test_options_takes_priority(self) -> None:
        opts = AnalysisOptions(subagent_model=_MODEL_OPUS)
        assert self._resolve(opts) == _MODEL_OPUS

    def test_env_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("QUODEQ_SUBAGENT_MODEL", _MODEL_SONNET)
        opts = AnalysisOptions()  # subagent_model is None
        assert self._resolve(opts) == _MODEL_SONNET

    def test_default_uses_client_model(self, monkeypatch) -> None:
        """No selection and no env var → None (AI CLI uses its own default model)."""
        monkeypatch.delenv("QUODEQ_SUBAGENT_MODEL", raising=False)
        opts = AnalysisOptions()
        assert self._resolve(opts) is None

    def test_options_beats_env(self, monkeypatch) -> None:
        monkeypatch.setenv("QUODEQ_SUBAGENT_MODEL", _MODEL_HAIKU)
        opts = AnalysisOptions(subagent_model=_MODEL_OPUS)
        assert self._resolve(opts) == _MODEL_OPUS

    def test_empty_string_falls_through(self, monkeypatch) -> None:
        """Empty string in options is falsy → should fall through to client default."""
        monkeypatch.delenv("QUODEQ_SUBAGENT_MODEL", raising=False)
        opts = AnalysisOptions(subagent_model="")
        assert self._resolve(opts) is None
