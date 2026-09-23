"""Every environment read under ``api/`` takes an injected mapping.

One pair of assertions per seam: ``env={"VAR": "value"}`` is honoured, and
``env={}`` means "no variables set" (the process value is ignored, never
resurrected by a truthiness fallback). ``create_app`` is the composition
root: it resolves the mapping once and hands it down, so the route-level
cases go through it rather than through a per-request parameter.
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask


def _quodeq_env(*omit: str) -> dict[str, str]:
    """The tmp-home QUODEQ_* vars the autouse isolation fixture set.

    ``create_app(env=...)`` bypasses ``os.environ`` entirely, so a bare
    ``{}`` would send the app at the developer's real ``~/.quodeq``. Start
    from the isolated home instead and add/omit only the variable under test.
    """
    return {
        k: v for k, v in os.environ.items()
        if k.startswith("QUODEQ_") and k not in omit
    }


# --------------------------------------------------------------------------
# Log-path resolution
# --------------------------------------------------------------------------

def test_ollama_log_path_honours_the_injected_env(monkeypatch, tmp_path: Path):
    from quodeq.api._ollama_log_routes import _ollama_log_path

    monkeypatch.setenv("QUODEQ_OLLAMA_LOG", str(tmp_path / "from-process.log"))
    injected = tmp_path / "from-env.log"
    assert _ollama_log_path({"QUODEQ_OLLAMA_LOG": str(injected)}) == injected
    assert _ollama_log_path({}) != tmp_path / "from-process.log"


def test_llamacpp_log_path_honours_the_injected_env(monkeypatch, tmp_path: Path):
    from quodeq.api._llamacpp_log_routes import _llamacpp_log_path

    monkeypatch.setenv("LLAMACPP_LOG_FILE", str(tmp_path / "from-process.log"))
    injected = tmp_path / "from-env.log"
    assert _llamacpp_log_path(env={"LLAMACPP_LOG_FILE": str(injected)}) == injected
    # env={} means the override is unset, so the probe falls through to the
    # default candidates -- never back to the process value.
    assert _llamacpp_log_path(env={}) != tmp_path / "from-process.log"


def test_default_log_paths_honours_the_injected_env(monkeypatch, tmp_path: Path):
    from quodeq.api import _llamacpp_log_routes as routes

    # XDG_STATE_HOME is the non-darwin, non-win32 branch; pin the platform
    # so the assertion means the same thing on every host.
    monkeypatch.setattr(routes.sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "from-process"))
    injected = tmp_path / "from-env"
    candidates = routes._default_log_paths({"XDG_STATE_HOME": str(injected)})
    assert injected / "llama-server.log" in candidates
    assert (tmp_path / "from-process" / "llama-server.log") not in routes._default_log_paths({})


# --------------------------------------------------------------------------
# Tail / stream tuning
# --------------------------------------------------------------------------

def test_log_tail_max_bytes_honours_the_injected_env(monkeypatch):
    from quodeq.api._log_tail_helpers import _DEFAULT_TAIL_MAX_BYTES, _tail_max_bytes

    monkeypatch.setenv("QUODEQ_LOG_TAIL_MAX_BYTES", "77")
    assert _tail_max_bytes({"QUODEQ_LOG_TAIL_MAX_BYTES": "4096"}) == 4096
    assert _tail_max_bytes({}) == _DEFAULT_TAIL_MAX_BYTES


def test_read_tail_honours_the_injected_byte_cap(tmp_path: Path):
    from quodeq.api._log_tail_helpers import read_tail

    log = tmp_path / "run.log"
    # Bytes, not text: on Windows write_text would emit \r\n and the 6-byte
    # cap would cut the first line in half.
    log.write_bytes(b"alpha\nbeta\n")
    lines, offset = read_tail(log, 0, {"QUODEQ_LOG_TAIL_MAX_BYTES": "6"})
    assert lines == ["alpha"]
    assert offset == 6
    assert read_tail(log, 0, {})[0] == ["alpha", "beta"]


def test_sse_tail_max_bytes_honours_the_injected_env(monkeypatch):
    from quodeq.api._sse_log_helpers import _DEFAULT_TAIL_MAX_BYTES, _tail_max_bytes

    monkeypatch.setenv("QUODEQ_LOG_TAIL_MAX_BYTES", "77")
    assert _tail_max_bytes(env={"QUODEQ_LOG_TAIL_MAX_BYTES": "2048"}) == 2048
    assert _tail_max_bytes(env={}) == _DEFAULT_TAIL_MAX_BYTES


def test_tick_ms_honours_the_injected_env(monkeypatch):
    from quodeq.api._run_event_stream import _tick_ms

    monkeypatch.setenv("QUODEQ_SSE_TICK_MS", "999")
    assert _tick_ms({"QUODEQ_SSE_TICK_MS": "0"}) == 0
    assert _tick_ms({}) == 250


def test_findings_batch_size_honours_the_injected_env(monkeypatch):
    from quodeq.api._run_event_watcher import DEFAULT_FINDINGS_BATCH, findings_batch_size

    monkeypatch.setenv("QUODEQ_SSE_FINDINGS_BATCH", "999")
    assert findings_batch_size({"QUODEQ_SSE_FINDINGS_BATCH": "5"}) == 5
    assert findings_batch_size({}) == DEFAULT_FINDINGS_BATCH


# --------------------------------------------------------------------------
# App creation
# --------------------------------------------------------------------------

def test_configure_logging_reads_verbose_from_the_injected_env(monkeypatch):
    from quodeq.api.app import _configure_logging

    monkeypatch.setenv("QUODEQ_VERBOSE", "1")
    assert _configure_logging(Flask(__name__), {"QUODEQ_VERBOSE": "1"})[1] is True
    assert _configure_logging(Flask(__name__), {})[1] is False


def test_create_app_hands_the_injected_env_to_the_log_routes(monkeypatch, tmp_path: Path):
    """The env reaches a route handler without being a request-time lookup."""
    from quodeq.api.app import create_app

    # An unset override still probes real fallback files, including /tmp.
    # Keep this environment-wiring test independent of installed providers.
    monkeypatch.setattr(
        "quodeq.api._llamacpp_log_routes._default_log_paths",
        lambda env: [tmp_path / "no-default.log"],
    )
    log_file = tmp_path / "llama.log"
    log_file.write_text("ready\n", encoding="utf-8")
    monkeypatch.setenv("LLAMACPP_LOG_FILE", str(log_file))

    injected = create_app(env={**_quodeq_env(), "LLAMACPP_LOG_FILE": str(log_file)})
    with injected.test_client() as c:
        assert c.get("/api/llamacpp/logs/available").get_json() == {"available": True}

    empty = create_app(env=_quodeq_env())
    with empty.test_client() as c:
        assert c.get("/api/llamacpp/logs/available").get_json() == {"available": False}


def test_create_app_hands_the_injected_env_to_the_ollama_log_route(monkeypatch, tmp_path: Path):
    """The Ollama twin of the llama.cpp case: registration-time env, no
    per-request parameter, and ``env={}`` does not see the process value."""
    from quodeq.api import _ollama_log_routes as routes
    from quodeq.api.app import create_app

    log_file = tmp_path / "server.log"
    log_file.write_text("[GIN] ready\n", encoding="utf-8")
    monkeypatch.setenv("QUODEQ_OLLAMA_LOG", str(log_file))

    injected = create_app(env={**_quodeq_env(), "QUODEQ_OLLAMA_LOG": str(log_file)})
    empty = create_app(env=_quodeq_env("QUODEQ_OLLAMA_LOG"))

    # Pin the no-override fallback (~/.ollama/logs/server.log) at an empty
    # dir so a developer who actually runs Ollama doesn't flip the second
    # half to 200, and keep the SSE generator finite.
    seen: list[Path] = []
    monkeypatch.setattr(routes.Path, "home", lambda: tmp_path / "no-ollama")
    monkeypatch.setattr(
        routes, "sse_tail_generator",
        lambda path, offset, **kw: seen.append(path) or iter(("data: ok\n\n",)),
    )

    with injected.test_client() as c:
        assert c.get("/api/ollama/logs/stream").status_code == 200
    assert seen == [log_file]

    with empty.test_client() as c:
        assert c.get("/api/ollama/logs/stream").status_code == 404
    assert seen == [log_file], "the empty mapping must not resurrect the process value"


def test_create_app_hands_the_injected_env_to_the_security_hooks(monkeypatch):
    from quodeq.api import security
    from quodeq.api.app import create_app

    token = "tok-injected"  # noqa: S105 — test fixture, not a credential
    ua = f"QuodeqDesktop/1.0 {security._WEBVIEW_TOKEN_UA_PREFIX}{token}"
    monkeypatch.setenv(security._ENV_WEBVIEW_TOKEN, token)

    empty = create_app(env=_quodeq_env(security._ENV_WEBVIEW_TOKEN))
    with empty.test_client() as c:
        csp = c.get("/api/health", headers={"User-Agent": ua}).headers["Content-Security-Policy"]
    assert "'unsafe-eval'" not in csp

    injected = create_app(env={**_quodeq_env(), security._ENV_WEBVIEW_TOKEN: token})
    with injected.test_client() as c:
        csp = c.get("/api/health", headers={"User-Agent": ua}).headers["Content-Security-Policy"]
    assert "'unsafe-eval'" in csp


def test_create_app_hands_the_injected_env_to_the_rate_limit_factory(tmp_path: Path):
    from quodeq.api._rate_limit_file_store import FileRateLimitStore
    from quodeq.api.app import _build_rate_limit_store

    store, _ = _build_rate_limit_store(env={
        "QUODEQ_RATE_LIMIT_BACKEND": "file",
        "QUODEQ_RATE_LIMIT_FILE": str(tmp_path / "limits.json"),
    })
    assert isinstance(store, FileRateLimitStore)
    assert not isinstance(_build_rate_limit_store(env={})[0], FileRateLimitStore)


def test_create_app_hands_the_injected_env_to_the_default_provider(monkeypatch, tmp_path: Path):
    """``_default_provider`` must not re-read ``os.environ`` after
    ``create_app`` already resolved the caller's env -- the index DB path
    comes from the injected mapping, not a monkeypatched process value."""
    from quodeq.api.app import create_app

    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "from-process" / "index.db"))

    injected = create_app(env={**_quodeq_env(), "QUODEQ_INDEX_DB_PATH": str(tmp_path / "index.db")})
    provider = injected.config["_provider"]
    assert provider._evaluations.index_db_path == tmp_path / "index.db"

    empty = create_app(env=_quodeq_env("QUODEQ_INDEX_DB_PATH"))
    empty_path = str(empty.config["_provider"]._evaluations.index_db_path)
    assert "from-process" not in empty_path


def test_configure_paths_and_cleanup_honours_the_injected_env(monkeypatch, tmp_path: Path):
    """Two different injected homes, neither of them the process one.

    ``env={}`` is not usable here: it would send the sweep at the
    developer's real ``~/.quodeq``. Two distinct mappings make the same
    point -- the value comes from the argument, not from ``os.environ``.
    """
    from quodeq.api.app import _configure_app

    from_process = tmp_path / "from-process"
    monkeypatch.setenv("QUODEQ_DIR", str(from_process))
    first, second = tmp_path / "first", tmp_path / "second"

    app_a = Flask(__name__)
    _configure_app(app_a, object(), None, {"QUODEQ_DIR": str(first)})
    assert app_a.config["ASSISTANT_DB_PATH"] == str(first / "assistant.db")

    app_b = Flask(__name__)
    _configure_app(app_b, object(), None, {"QUODEQ_DIR": str(second)})
    assert app_b.config["ASSISTANT_DB_PATH"] == str(second / "assistant.db")

    assert str(from_process) not in app_a.config["ASSISTANT_DB_PATH"]
    assert str(from_process) not in app_b.config["ASSISTANT_DB_PATH"]
