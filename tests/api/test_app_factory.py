"""Tests for the Flask app factory and health endpoint."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from quodeq.api.app import create_app, _default_provider


class _StubProvider:
    """Minimal provider for testing app creation without filesystem."""

    def list_projects(self, reports_dir):
        return {"projects": []}

    def get_project_info(self, reports_dir, project):
        return {}

    def update_project_path(self, reports_dir, project, new_path):
        return False

    def delete_project(self, reports_dir, project):
        return False

    def clone_to_local(self, reports_dir, project, destination):
        return None

    def start_evaluation(self, *a, **kw):
        return None

    def get_job_status(self, *a, **kw):
        return None

    def list_evaluations(self, *a, **kw):
        return []


class TestCreateApp:
    def test_creates_flask_app(self):
        app = create_app(provider=_StubProvider())
        assert app is not None
        assert app.config["_provider"] is not None

    def test_test_config_applied(self):
        app = create_app(provider=_StubProvider(), test_config={"MY_KEY": "val"})
        assert app.config["MY_KEY"] == "val"

    def test_health_endpoint(self):
        app = create_app(provider=_StubProvider())
        client = app.test_client()
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "version" in data
        assert "host" in data
        assert "port" in data
        assert "address" in data

    def test_health_verbose_includes_pid(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_VERBOSE", "1")
        app = create_app(provider=_StubProvider())
        client = app.test_client()
        resp = client.get("/api/health")
        data = resp.get_json()
        assert "pid" in data
        assert data["pid"] == os.getpid()

    def test_health_non_verbose_no_pid(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_VERBOSE", raising=False)
        app = create_app(provider=_StubProvider())
        client = app.test_client()
        resp = client.get("/api/health")
        data = resp.get_json()
        assert "pid" not in data

    def test_health_display_host_localhost(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_ACTION_API_HOST", "127.0.0.1")
        app = create_app(provider=_StubProvider())
        client = app.test_client()
        resp = client.get("/api/health")
        data = resp.get_json()
        assert "localhost" in data["address"]

    def test_health_display_host_custom(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_ACTION_API_HOST", "10.0.0.1")
        app = create_app(provider=_StubProvider())
        client = app.test_client()
        resp = client.get("/api/health")
        data = resp.get_json()
        assert "10.0.0.1" in data["address"]

    def test_sets_standards_config(self):
        app = create_app(provider=_StubProvider())
        assert "STANDARDS_EVALUATORS_DIR" in app.config
        assert "STANDARDS_COMPILED_DIR" in app.config
        assert "STANDARDS_DIMENSIONS_FILE" in app.config

    def test_skips_standards_config_if_set(self):
        app = create_app(
            provider=_StubProvider(),
            test_config={"STANDARDS_EVALUATORS_DIR": "/custom"},
        )
        assert app.config["STANDARDS_EVALUATORS_DIR"] == "/custom"

    def test_default_provider_returns_filesystem(self):
        prov = _default_provider()
        assert prov is not None


class TestMainFunction:
    def test_main_runs_app(self, monkeypatch):
        """Verify main() creates app and calls app.run().

        Patches signal.signal too: main() registers a SIGINT/SIGTERM
        handler that raises SystemExit(0). Letting the real handler leak
        into the rest of the test process means pytest-timeout's
        watchdog (which sends SIGINT to the main thread on timeout) hits
        that handler instead of pytest's own KeyboardInterrupt path,
        crashing pytest with INTERNALERROR mid-suite. Surfaced on
        Windows where a slow test triggered the watchdog.
        """
        mock_run = MagicMock()
        with patch("quodeq.api.app.create_app") as mock_create, \
             patch("quodeq.api.app.signal.signal") as mock_signal:
            mock_app = MagicMock()
            mock_app.run = mock_run
            mock_app.config = {"_provider": MagicMock()}
            mock_create.return_value = mock_app
            from quodeq.api.app import main
            main(env={"QUODEQ_API_KEY": "test-key"})
            mock_create.assert_called_once()
            mock_run.assert_called_once()
            assert mock_signal.called, "main() should install signal handlers"
