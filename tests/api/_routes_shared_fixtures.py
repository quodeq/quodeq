"""Shared fixtures for tests/api/test_routes_shared_*.py siblings.

Split out of test_routes_shared.py.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app
from quodeq.services import shared_publish

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evaluations"))
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_publish_status(monkeypatch):
    """Give each test a fresh module-default PublishStatus.

    The routes read the module default, still shared process-wide in
    production, so each test here swaps in its own instance to stay
    hermetic across the whole suite.
    """
    monkeypatch.setattr(shared_publish, "_default_status", shared_publish.PublishStatus())
