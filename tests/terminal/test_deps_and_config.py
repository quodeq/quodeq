"""Dependency + config-plumbing regression tests for the embedded terminal feature."""
from __future__ import annotations


def test_flask_sock_importable():
    import flask_sock  # noqa: F401


def test_create_app_stashes_gate_inputs():
    from quodeq.api.app import create_app
    app = create_app(api_key=None, test_config={"STANDARDS_EVALUATORS_DIR": "/tmp/e",
                     "STANDARDS_COMPILED_DIR": "/tmp/c", "STANDARDS_DIMENSIONS_FILE": "/tmp/d.json",
                     "ASSISTANT_DB_PATH": "/tmp/a.db"})
    assert "QUODEQ_API_KEY" in app.config
    assert "QUODEQ_BIND_HOST" in app.config
