"""CI env seams: GITHUB_TOKEN comes from handle_ci's env, read once."""
from __future__ import annotations

import argparse

from quodeq.ci.cli import _resolve_report_token, handle_ci
from quodeq.ci.reporter import _DEFAULT_GITHUB_API, _github_api_base


def _args(**kwargs) -> argparse.Namespace:
    base = dict(ci_action="report", token=None, evaluation_dir="/does/not/exist")
    base.update(kwargs)
    return argparse.Namespace(**base)


class TestGithubApiBase:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_GITHUB_API_BASE", "https://from-process")
        assert _github_api_base({"QUODEQ_GITHUB_API_BASE": "https://from-env"}) == "https://from-env"

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_GITHUB_API_BASE", "https://from-process")
        assert _github_api_base({}) == _DEFAULT_GITHUB_API


class TestResolveReportToken:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "from-process")
        assert _resolve_report_token(_args(), {"GITHUB_TOKEN": "from-env"}) == "from-env"

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_TOKEN", "from-process")
        assert _resolve_report_token(_args(), {}) is None
        assert "GITHUB_TOKEN environment variable required" in capsys.readouterr().err

    def test_explicit_token_still_wins(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "from-process")
        assert _resolve_report_token(_args(token="flag"), {"GITHUB_TOKEN": "from-env"}) == "flag"


class TestHandleCiThreadsEnv:
    def test_injected_token_gets_past_the_token_check(self, monkeypatch, capsys):
        """A missing evaluation dir is the NEXT failure, so the token resolved."""
        monkeypatch.setenv("GITHUB_TOKEN", "")
        assert handle_ci(_args(), {"GITHUB_TOKEN": "from-env"}) == 1
        assert "evaluation directory not found" in capsys.readouterr().err

    def test_empty_injected_env_fails_on_the_token(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_TOKEN", "from-process")
        assert handle_ci(_args(), {}) == 1
        assert "GITHUB_TOKEN environment variable required" in capsys.readouterr().err
