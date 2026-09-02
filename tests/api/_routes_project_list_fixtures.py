"""Shared fixtures for tests/api/test_routes_project_list_*.py siblings.

Split out of test_routes_project_list.py.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from quodeq.api.routes_project_list import register_project_list_routes


class _FakeProvider:
    """Minimal stub implementing the ActionProvider methods used by project routes."""

    def __init__(self):
        self.projects: list[dict] = []
        self.deleted: list[str] = []
        self.updated_paths: dict[str, str] = {}
        self.project_info: dict | None = None

    def list_projects(self, reports_dir: str) -> dict:
        return {"projects": self.projects}

    def delete_project(self, reports_dir: str, project: str) -> bool:
        if project in self.deleted:
            return False
        self.deleted.append(project)
        return True

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        self.updated_paths[project] = new_path
        return True

    def get_project_info(self, reports_dir: str, project: str) -> dict:
        return self.project_info or {}

    def invalidate_projects_cache(self) -> None:
        self.cache_invalidated = True

    def create_project(self, reports_dir: str, spec):
        # Delegates to the real use case (same as FilesystemActionProvider):
        # there is no filesystem-specific behavior to fake here, only the
        # clone/scan primitives the tests monkeypatch directly.
        from quodeq.services.project_registration import register_project_with_rollback
        return register_project_with_rollback(reports_dir, spec)


@pytest.fixture()
def provider():
    return _FakeProvider()


@pytest.fixture()
def app(tmp_path, provider):
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["EVALUATIONS_DIR"] = str(tmp_path)

    with patch("quodeq.api.routes_project_list.reports_dir", return_value=str(tmp_path)):
        register_project_list_routes(flask_app, provider)
        yield flask_app


@pytest.fixture()
def client(app):
    # The app fixture already holds the reports_dir patch open via yield
    return app.test_client()
