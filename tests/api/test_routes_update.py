from unittest.mock import patch

import pytest
from flask import Flask

from quodeq.api.routes_update import register_update_routes


@pytest.fixture()
def client():
    app = Flask(__name__)
    register_update_routes(app)
    return app.test_client()


_STATUS = {"current": "1.4.0", "latest": "1.5.0", "update_available": True}


def test_get_status(client) -> None:
    with patch("quodeq.api.routes_update.get_status", return_value=_STATUS), \
         patch("quodeq.api.routes_update.check_async"):
        resp = client.get("/api/update/status")
    assert resp.status_code == 200
    assert resp.get_json()["latest"] == "1.5.0"


def test_post_check_forces(client) -> None:
    with patch("quodeq.api.routes_update.run_check") as run, \
         patch("quodeq.api.routes_update.get_status", return_value=_STATUS):
        resp = client.post("/api/update/check")
    assert resp.status_code == 200
    run.assert_called_once_with(force=True)


def test_post_dismiss_requires_version(client) -> None:
    resp = client.post("/api/update/dismiss", json={})
    assert resp.status_code == 400


def test_post_dismiss_ok(client) -> None:
    with patch("quodeq.api.routes_update.dismiss") as dis, \
         patch("quodeq.api.routes_update.get_status", return_value=_STATUS):
        resp = client.post("/api/update/dismiss", json={"version": "1.5.0"})
    assert resp.status_code == 200
    dis.assert_called_once_with("1.5.0")


def _status_with_self_update(supported: bool, **extra) -> dict:
    return {
        **_STATUS,
        "download_url": "https://example.com/Quodeq-1.5.0-macOS.dmg",
        "self_update": {"supported": supported, "reason": None if supported else "no_team_id"},
        **extra,
    }


def test_post_selfupdate_starts(client) -> None:
    with patch(
        "quodeq.api.routes_update.get_status",
        return_value=_status_with_self_update(True),
    ), patch("quodeq.api.routes_update.start_self_update", return_value=True) as start:
        resp = client.post("/api/update/selfupdate")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    start.assert_called_once_with("https://example.com/Quodeq-1.5.0-macOS.dmg", "1.5.0")


def test_post_selfupdate_unsupported_409(client) -> None:
    with patch(
        "quodeq.api.routes_update.get_status",
        return_value=_status_with_self_update(False),
    ):
        resp = client.post("/api/update/selfupdate")
    assert resp.status_code == 409
    assert resp.get_json()["reason"] == "no_team_id"


def test_post_selfupdate_no_update_409(client) -> None:
    status = _status_with_self_update(True, update_available=False)
    with patch("quodeq.api.routes_update.get_status", return_value=status):
        resp = client.post("/api/update/selfupdate")
    assert resp.status_code == 409


def test_post_selfupdate_busy_409(client) -> None:
    with patch(
        "quodeq.api.routes_update.get_status",
        return_value=_status_with_self_update(True),
    ), patch("quodeq.api.routes_update.start_self_update", return_value=False):
        resp = client.post("/api/update/selfupdate")
    assert resp.status_code == 409


def test_post_settings_toggles(client) -> None:
    with patch("quodeq.api.routes_update.set_settings") as setn, \
         patch("quodeq.api.routes_update.get_status", return_value=_STATUS):
        resp = client.post("/api/update/settings", json={"auto_check_enabled": False, "disclosed": True})
    assert resp.status_code == 200
    setn.assert_called_once_with(auto_check_enabled=False, disclosed=True)
