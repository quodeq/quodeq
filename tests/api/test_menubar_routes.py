"""/api/menubar — menu bar preference and process control endpoints."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.api.app import create_app
from quodeq.menubar import control


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    app = create_app()
    with app.test_client() as c:
        yield c


def test_get_reports_status(client):
    with patch.object(control, "is_supported", return_value=True), \
         patch.object(control, "is_running", return_value=False):
        resp = client.get("/api/menubar")
    assert resp.status_code == 200
    assert resp.get_json() == {"supported": True, "enabled": False, "running": False}


def test_put_true_persists_and_spawns(client):
    with patch.object(control, "is_supported", return_value=True), \
         patch.object(control, "is_running", return_value=True), \
         patch.object(control, "spawn") as spawn, \
         patch.object(control, "stop") as stop:
        resp = client.put("/api/menubar", json={"enabled": True}, headers={"Origin": "http://localhost"})
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is True
    spawn.assert_called_once()
    stop.assert_not_called()


def test_put_false_persists_and_stops(client):
    with patch.object(control, "is_supported", return_value=True), \
         patch.object(control, "is_running", return_value=False), \
         patch.object(control, "spawn") as spawn, \
         patch.object(control, "stop") as stop:
        resp = client.put("/api/menubar", json={"enabled": False}, headers={"Origin": "http://localhost"})
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is False
    stop.assert_called_once()
    spawn.assert_not_called()


@pytest.mark.parametrize("body", [{}, {"enabled": "yes"}, {"enabled": 1}, None])
def test_put_rejects_non_bool(client, body):
    with patch.object(control, "spawn") as spawn, patch.object(control, "stop") as stop:
        resp = client.put("/api/menubar", json=body, headers={"Origin": "http://localhost"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_PARAM"
    spawn.assert_not_called()
    stop.assert_not_called()
