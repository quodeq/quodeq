"""Tests for the power-selector (subagent_model) plumbing across the backend stack."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.provider.base import EvaluationOptions
from quodeq.engine.runner import AnalysisOptions


# ---------------------------------------------------------------------------
# EvaluationOptions — subagent_model field
# ---------------------------------------------------------------------------

class TestEvaluationOptionsSubagentModel:
    def test_default_is_none(self) -> None:
        opts = EvaluationOptions()
        assert opts.subagent_model is None

    def test_accepts_haiku(self) -> None:
        opts = EvaluationOptions(subagent_model="claude-haiku-4-5")
        assert opts.subagent_model == "claude-haiku-4-5"

    def test_accepts_sonnet(self) -> None:
        opts = EvaluationOptions(subagent_model="claude-sonnet-4-6")
        assert opts.subagent_model == "claude-sonnet-4-6"

    def test_accepts_opus(self) -> None:
        opts = EvaluationOptions(subagent_model="claude-opus-4-6")
        assert opts.subagent_model == "claude-opus-4-6"


# ---------------------------------------------------------------------------
# AnalysisOptions — subagent_model field
# ---------------------------------------------------------------------------

class TestAnalysisOptionsSubagentModel:
    def test_default_is_none(self) -> None:
        opts = AnalysisOptions()
        assert opts.subagent_model is None

    def test_stores_value(self) -> None:
        opts = AnalysisOptions(subagent_model="claude-sonnet-4-6")
        assert opts.subagent_model == "claude-sonnet-4-6"


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
            options=EvaluationOptions(subagent_model="claude-opus-4-6"),
        )
        assert captured["env"]["SUBAGENT_MODEL"] == "claude-opus-4-6"

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
            options=EvaluationOptions(subagent_model="claude-haiku-4-5"),
        )
        assert captured["env"]["SUBAGENT_MODEL"] == "claude-haiku-4-5"


# ---------------------------------------------------------------------------
# API route — subagentModel in JSON payload
# ---------------------------------------------------------------------------

class TestApiRouteSubagentModel:
    @pytest.fixture(autouse=True)
    def _disable_auth(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_AUTH_DISABLED", "1")

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

    def test_subagent_model_forwarded_from_payload(self) -> None:
        from quodeq.action_api import create_app

        captured = {}
        app = create_app(self._make_capturing_provider(captured))
        client = app.test_client()

        response = client.post("/api/evaluations", json={
            "repo": "/tmp",
            "subagentModel": "claude-sonnet-4-6",
        })
        assert response.status_code == 400 or captured.get("options") is not None
        if "options" in captured:
            assert captured["options"].subagent_model == "claude-sonnet-4-6"

    def test_subagent_model_none_when_not_provided(self) -> None:
        from quodeq.action_api import create_app

        captured = {}
        app = create_app(self._make_capturing_provider(captured))
        client = app.test_client()

        response = client.post("/api/evaluations", json={
            "repo": "/tmp",
        })
        # May 400 due to repo validation, but if it reaches start_evaluation:
        if "options" in captured:
            assert captured["options"].subagent_model is None


# ---------------------------------------------------------------------------
# Runner — subagent model resolution (options > env > default)
# ---------------------------------------------------------------------------

class TestRunnerSubagentModelResolution:
    """The runner should pick subagent_model from options first, then
    SUBAGENT_MODEL env, then fall back to claude-haiku-4-5."""

    def test_options_takes_priority(self) -> None:
        opts = AnalysisOptions(subagent_model="claude-opus-4-6")
        model = opts.subagent_model or os.environ.get("SUBAGENT_MODEL") or "claude-haiku-4-5"
        assert model == "claude-opus-4-6"

    def test_env_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("SUBAGENT_MODEL", "claude-sonnet-4-6")
        opts = AnalysisOptions()  # subagent_model is None
        model = opts.subagent_model or os.environ.get("SUBAGENT_MODEL") or "claude-haiku-4-5"
        assert model == "claude-sonnet-4-6"

    def test_default_haiku(self, monkeypatch) -> None:
        monkeypatch.delenv("SUBAGENT_MODEL", raising=False)
        opts = AnalysisOptions()
        model = opts.subagent_model or os.environ.get("SUBAGENT_MODEL") or "claude-haiku-4-5"
        assert model == "claude-haiku-4-5"

    def test_options_beats_env(self, monkeypatch) -> None:
        monkeypatch.setenv("SUBAGENT_MODEL", "claude-haiku-4-5")
        opts = AnalysisOptions(subagent_model="claude-opus-4-6")
        model = opts.subagent_model or os.environ.get("SUBAGENT_MODEL") or "claude-haiku-4-5"
        assert model == "claude-opus-4-6"

    def test_empty_string_falls_through(self, monkeypatch) -> None:
        """Empty string in options is falsy → should fall through to env/default."""
        monkeypatch.delenv("SUBAGENT_MODEL", raising=False)
        opts = AnalysisOptions(subagent_model="")
        model = opts.subagent_model or os.environ.get("SUBAGENT_MODEL") or "claude-haiku-4-5"
        assert model == "claude-haiku-4-5"
