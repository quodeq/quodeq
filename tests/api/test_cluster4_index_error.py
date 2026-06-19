"""Finding #523 — /api/index/rebuild must return structured JSON 500 on failure.

When provider.rebuild_index() raises, the route previously let the exception
propagate as a plain 500. After the fix it must return
{"error": ..., "code": "INTERNAL_ERROR"} with status 500.
"""
from __future__ import annotations

from http import HTTPStatus
from unittest.mock import MagicMock

import pytest

from quodeq.api.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    broken_provider = MagicMock()
    broken_provider.rebuild_index.side_effect = RuntimeError("index exploded")
    # Pass provider directly so create_app stores it in app.config["_provider"];
    # passing via test_config is overwritten by the provider= assignment in app.py.
    app = create_app(provider=broken_provider, test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


def test_rebuild_index_returns_json_500_on_unexpected_error(client):
    """rebuild_index() raising must yield a structured JSON 500, not a bare exception."""
    resp = client.post("/api/index/rebuild", headers={"Origin": "http://localhost"})

    assert resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    data = resp.get_json()
    assert data is not None, "Response body must be JSON"
    assert "error" in data
    assert "code" in data
