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


def test_post_settings_toggles(client) -> None:
    with patch("quodeq.api.routes_update.set_settings") as setn, \
         patch("quodeq.api.routes_update.get_status", return_value=_STATUS):
        resp = client.post("/api/update/settings", json={"auto_check_enabled": False, "disclosed": True})
    assert resp.status_code == 200
    setn.assert_called_once_with(auto_check_enabled=False, disclosed=True)
