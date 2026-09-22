"""Shared fixtures for tests/api/test_assistant_workspace_routes*.py siblings."""
from __future__ import annotations

import pytest
from flask import Flask

from quodeq.api.assistant_routes import register_assistant_routes
from quodeq.assistant.worktree import ensure_session_worktree, _run
from quodeq.data.sqlite.assistant_repository import AssistantRepository


@pytest.fixture()
def app(tmp_path, monkeypatch):
    catalog = {"ollama": {"type": "api", "api_base": "http://localhost:11434/v1"}}
    monkeypatch.setattr(
        "quodeq.api.assistant_routes.get_provider_configs", lambda: catalog)
    monkeypatch.setenv("QUODEQ_WORKTREES_DIR", str(tmp_path / "wts"))
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["ASSISTANT_DB_PATH"] = str(tmp_path / "assistant.db")
    app.config["STANDARDS_EVALUATORS_DIR"] = str(tmp_path / "evaluators")
    app.config["STANDARDS_COMPILED_DIR"] = str(tmp_path / "compiled")
    app.config["STANDARDS_DIMENSIONS_FILE"] = str(tmp_path / "dimensions.json")
    register_assistant_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _run(["git", "-C", str(root), "init", "-q", "-b", "main"])
    _run(["git", "-C", str(root), "config", "core.autocrlf", "false"])
    _run(["git", "-C", str(root), "config", "user.name", "T"])
    _run(["git", "-C", str(root), "config", "user.email", "t@example.com"])
    (root / "app.py").write_bytes(b"x = 1\n")
    _run(["git", "-C", str(root), "add", "-A"])
    _run(["git", "-C", str(root), "commit", "-q", "-m", "init"])
    return root


def _session_with_worktree(app, client, repo):
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama"}).get_json()["sessionId"]
    store = AssistantRepository(app.config["ASSISTANT_DB_PATH"])
    manager = ensure_session_worktree(store, repo_root=repo, project_id="proj",
                                      session_id=sid)
    (manager.path / "app.py").write_bytes(b"x = 2\n")
    return sid, store, manager
