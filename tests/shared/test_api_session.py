"""The session file the local API hands its secret over with."""
from __future__ import annotations

import os
import sys

import pytest

from quodeq.shared import api_session


def test_the_file_round_trips_and_is_private_to_this_user(tmp_path):
    env = {"QUODEQ_RUN_DIR": str(tmp_path / "run")}
    path = api_session.write_session_file(7866, "s3cret", env)
    assert api_session.read_session_file(7866, env) == "s3cret"
    assert path.parent == tmp_path / "run"
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in path.parent.iterdir()] == ["api-7866.session"], "no temp file left behind"


def test_a_missing_file_reads_as_none(tmp_path):
    assert api_session.read_session_file(7866, {"QUODEQ_RUN_DIR": str(tmp_path)}) is None


def test_removal_leaves_a_newer_apis_file_alone(tmp_path):
    env = {"QUODEQ_RUN_DIR": str(tmp_path)}
    api_session.write_session_file(7866, "newer", env)
    api_session.remove_session_file(7866, "older", env)
    assert api_session.read_session_file(7866, env) == "newer"
    api_session.remove_session_file(7866, "newer", env)
    assert api_session.read_session_file(7866, env) is None


@pytest.mark.parametrize("url, expected", [
    ("http://127.0.0.1:7866", {api_session.SESSION_HEADER: "s3cret"}),
    ("http://127.0.0.1:7867", {}),
    ("http://127.0.0.1", {}),
    ("http://[::1", {}),
])
def test_session_headers_follow_the_port_in_the_url(tmp_path, url, expected):
    env = {"QUODEQ_RUN_DIR": str(tmp_path)}
    api_session.write_session_file(7866, "s3cret", env)
    assert api_session.session_headers(url, env) == expected


def test_publish_session_writes_the_apps_secret_and_registers_its_removal(tmp_path, monkeypatch):
    from quodeq.api import session_auth
    from quodeq.api.app import create_app

    env = {"QUODEQ_RUN_DIR": str(tmp_path), "QUODEQ_ACTION_API_PORT": "7871"}
    app = create_app(env=env)
    registered = []
    monkeypatch.setattr(session_auth.atexit, "register", lambda *a: registered.append(a))
    session_auth.publish_session(app, env)

    secret = app.extensions["session_auth"].secret
    assert api_session.read_session_file(7871, env) == secret
    assert registered == [(api_session.remove_session_file, 7871, secret, env)]
    assert secret not in os.environ.values()


def test_a_failed_write_leaves_no_temp_file_behind(tmp_path):
    env = {"QUODEQ_RUN_DIR": str(tmp_path)}
    with pytest.raises(UnicodeEncodeError):
        api_session.write_session_file(7866, "sécret", env)
    assert list(tmp_path.iterdir()) == []
