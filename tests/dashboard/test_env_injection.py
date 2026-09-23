"""Every environment read under ``dashboard/`` takes an injected mapping.

One pair of assertions per seam: ``env={"VAR": "value"}`` is honoured, and
``env={}`` means "no variables set" (the process value is ignored, never
resurrected by a truthiness fallback).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.dashboard import _api_spawn, _build_npm
from quodeq.dashboard._api_spawn import spawn_action_api

from tests.conftest import DummyProcess

pytestmark = pytest.mark.usefixtures("restore_environ")

_TEST_PORT = 7863
_TEST_HOST = "127.0.0.1"


def _capture_popen(monkeypatch) -> dict:
    captured: dict = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["env"] = env
        return DummyProcess()

    monkeypatch.setattr(_api_spawn.subprocess, "Popen", fake_popen)
    return captured


# --------------------------------------------------------------------------
# API subprocess spawn
# --------------------------------------------------------------------------

def test_spawn_action_api_inherits_the_injected_env(monkeypatch, tmp_path: Path):
    captured = _capture_popen(monkeypatch)
    monkeypatch.setenv("QUODEQ_FROM_PROCESS", "leaked")

    spawn_action_api(
        _TEST_PORT, tmp_path / "a.pid", _TEST_HOST,
        env={"QUODEQ_FROM_ENV": "injected"},
    )
    assert captured["env"]["QUODEQ_FROM_ENV"] == "injected"
    assert "QUODEQ_FROM_PROCESS" not in captured["env"]


def test_spawn_action_api_treats_an_empty_env_as_empty(monkeypatch, tmp_path: Path):
    """``env={}`` must not fall back to the process environment."""
    captured = _capture_popen(monkeypatch)
    monkeypatch.setenv("QUODEQ_FROM_PROCESS", "leaked")

    spawn_action_api(_TEST_PORT, tmp_path / "a.pid", _TEST_HOST, env={})
    assert "QUODEQ_FROM_PROCESS" not in captured["env"]
    # The variables the spawn itself sets are still there.
    assert captured["env"]["QUODEQ_ACTION_API_PORT"] == str(_TEST_PORT)


# --------------------------------------------------------------------------
# npm build
# --------------------------------------------------------------------------

def test_run_npm_build_passes_the_injected_env_to_the_child(monkeypatch, tmp_path: Path):
    calls: list[dict] = []
    monkeypatch.setattr(_build_npm.shutil, "which", lambda _name: "/usr/bin/npm")
    monkeypatch.setattr(
        _build_npm.subprocess, "run",
        lambda cmd, **kwargs: calls.append(kwargs) or None,
    )
    monkeypatch.setenv("QUODEQ_FROM_PROCESS", "leaked")
    static_dir = tmp_path / "static"

    _build_npm.run_npm_build(tmp_path, static_dir, env={"QUODEQ_FROM_ENV": "injected"})
    build_env = calls[-1]["env"]
    assert build_env["QUODEQ_BUILD_OUTDIR"] == str(static_dir)
    assert build_env["QUODEQ_FROM_ENV"] == "injected"
    assert "QUODEQ_FROM_PROCESS" not in build_env

    calls.clear()
    _build_npm.run_npm_build(tmp_path, static_dir, env={})
    assert calls[-1]["env"] == {"QUODEQ_BUILD_OUTDIR": str(static_dir)}


def test_run_npm_build_reads_its_timeouts_from_the_injected_env(monkeypatch, tmp_path: Path):
    calls: list[dict] = []
    monkeypatch.setattr(_build_npm.shutil, "which", lambda _name: "/usr/bin/npm")
    monkeypatch.setattr(
        _build_npm.subprocess, "run",
        lambda cmd, **kwargs: calls.append(kwargs) or None,
    )
    monkeypatch.setenv("QUODEQ_NPM_INSTALL_TIMEOUT_S", "11")
    monkeypatch.setenv("QUODEQ_NPM_BUILD_TIMEOUT_S", "12")

    _build_npm.run_npm_build(tmp_path, tmp_path / "static", env={
        "QUODEQ_NPM_INSTALL_TIMEOUT_S": "3", "QUODEQ_NPM_BUILD_TIMEOUT_S": "4",
    })
    assert [c["timeout"] for c in calls] == [3, 4]

    calls.clear()
    _build_npm.run_npm_build(tmp_path, tmp_path / "static", env={})
    assert [c["timeout"] for c in calls] == [300, 600]


def test_quodeq_dir_honours_the_injected_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path / "from-process"))
    assert _build_npm.quodeq_dir({"QUODEQ_DIR": str(tmp_path)}) == tmp_path
    assert _build_npm.quodeq_dir({}) == Path.home() / ".quodeq"


# --------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------

def test_local_hosts_honours_the_injected_env(monkeypatch):
    from quodeq.dashboard._networking import local_host_names

    monkeypatch.setenv("QUODEQ_LOCAL_HOSTS", "from-process")
    assert "from-env" in local_host_names({"QUODEQ_LOCAL_HOSTS": "from-env"})
    assert "from-process" not in local_host_names({})


def test_allow_plaintext_http_honours_the_injected_env(monkeypatch):
    from quodeq.dashboard._networking import allow_plaintext_http

    monkeypatch.setenv("QUODEQ_ALLOW_PLAINTEXT_HTTP", "1")
    assert allow_plaintext_http(env={"QUODEQ_ALLOW_PLAINTEXT_HTTP": "1"}) is True
    assert allow_plaintext_http(env={}) is False


# --------------------------------------------------------------------------
# Launch-token hand-off
# --------------------------------------------------------------------------

def test_ensure_action_api_writes_the_launch_token_into_the_injected_env(monkeypatch):
    import os

    from quodeq.dashboard._server import ensure_action_api
    from quodeq.dashboard._webview_token import ENV_WEBVIEW_TOKEN
    from quodeq.dashboard._probes import ApiProbes

    monkeypatch.delenv(ENV_WEBVIEW_TOKEN, raising=False)
    probes = ApiProbes(
        local_hosts=lambda *a, **k: {"127.0.0.1"},
        is_port_open=lambda *_a: False,
        spawn=lambda port, url, cfg: (url, None),
    )
    target: dict[str, str] = {}
    ensure_action_api("127.0.0.1", 8000, probes=probes, env=target)

    assert target[ENV_WEBVIEW_TOKEN]
    assert ENV_WEBVIEW_TOKEN not in os.environ


def test_ensure_action_api_forced_writes_the_launch_token_into_the_injected_env(monkeypatch):
    import os

    from quodeq.dashboard._server import ensure_action_api_forced
    from quodeq.dashboard._webview_token import ENV_WEBVIEW_TOKEN
    from quodeq.dashboard._probes import ApiProbes

    monkeypatch.delenv(ENV_WEBVIEW_TOKEN, raising=False)
    probes = ApiProbes(
        local_hosts=lambda *a, **k: {"127.0.0.1"},
        is_port_open=lambda *_a: False,
        spawn=lambda port, url, cfg: (url, None),
    )
    target: dict[str, str] = {}
    ensure_action_api_forced("127.0.0.1", 5000, probes=probes, env=target)

    assert target[ENV_WEBVIEW_TOKEN]
    assert ENV_WEBVIEW_TOKEN not in os.environ
