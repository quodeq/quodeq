"""Tests for quodeq.dashboard._server — API startup and forced-port mode.

Split when this file crossed the 300-line cap: the serve modes (browser,
blocking, native) now live in test_server_serve_modes.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.dashboard._probes import ApiProbes


class TestEnsureActionApi:
    def test_reuses_existing_healthy_api(self):
        from quodeq.dashboard._server import _ensure_action_api
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            api_healthy=lambda *_a: True,
            is_port_open=lambda *_a: True,
        )
        url, proc = _ensure_action_api("127.0.0.1", 8000, probes=probes)
        assert url == "http://127.0.0.1:8000"
        assert proc is None

    def test_reuse_warns_about_the_webview_token_mismatch(self, caplog):
        """QUODEQ_WEBVIEW_TOKEN is only set on the spawn branch, so a reused
        API keeps its own launch token while the webview we open next gets a
        fresh one. _is_trusted_webview then fails closed (correct) and the
        native shell's JS bridge silently stops working — that needs a
        diagnostic, or it is impossible to explain.
        """
        from quodeq.dashboard import _server
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            api_healthy=lambda *_a: True,
            is_port_open=lambda *_a: True,
        )
        with patch.object(_server, "_warn_reused_api_token_mismatch") as warn:
            _server._ensure_action_api("127.0.0.1", 8000, probes=probes)
        warn.assert_called_once_with("http://127.0.0.1:8000")

    def test_reuse_warning_names_the_csp_relaxation(self, caplog):
        from quodeq.dashboard import _webview_token
        with caplog.at_level("WARNING", logger="quodeq.dashboard._webview_token"):
            _webview_token._warn_reused_api_token_mismatch("http://127.0.0.1:8000")
        message = " ".join(r.getMessage() for r in caplog.records)
        assert "http://127.0.0.1:8000" in message
        assert "unsafe-eval" in message

    def test_spawns_new_api(self):
        from quodeq.dashboard._server import _ensure_action_api
        spawn = MagicMock(return_value=("http://127.0.0.1:8000", MagicMock()))
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            is_port_open=lambda *_a: False,
            spawn=spawn,
        )
        url, proc = _ensure_action_api("127.0.0.1", 8000, probes=probes)
        assert url == "http://127.0.0.1:8000"
        spawn.assert_called_once()

    def test_skips_unhealthy_port_tries_next(self):
        from quodeq.dashboard._server import _ensure_action_api
        # Port 8000 is open but unhealthy, port 7863 is closed so it spawns
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            api_healthy=lambda *_a: False,
            is_port_open=MagicMock(side_effect=[True, False]),
            spawn=lambda *_a, **_k: ("http://127.0.0.1:7863", MagicMock()),
        )
        url, proc = _ensure_action_api("127.0.0.1", 8000, max_tries=2, probes=probes)
        assert "7863" in url

    def test_raises_when_no_free_port(self):
        from quodeq.dashboard._server import _ensure_action_api
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            api_healthy=lambda *_a: False,
            is_port_open=lambda *_a: True,
        )
        with pytest.raises(RuntimeError, match="Unable to find a free port"):
            _ensure_action_api("127.0.0.1", 8000, max_tries=2, probes=probes)

    def test_rejects_non_localhost_without_tls(self):
        from quodeq.dashboard._server import _ensure_action_api
        probes = ApiProbes(local_hosts=lambda *a, **k: {"127.0.0.1"})
        with patch("quodeq.dashboard._server._allow_plaintext_http", return_value=False):
            with pytest.raises(RuntimeError, match="Plaintext HTTP"):
                _ensure_action_api("192.168.1.100", 8000, probes=probes)

    def test_allows_non_localhost_with_opt_in(self):
        from quodeq.dashboard._server import _ensure_action_api
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1"},
            is_port_open=lambda *_a: False,
            spawn=lambda *_a, **_k: ("http://192.168.1.100:8000", MagicMock()),
        )
        with patch("quodeq.dashboard._server._allow_plaintext_http", return_value=True):
            url, proc = _ensure_action_api("192.168.1.100", 8000, probes=probes)
        assert "192.168.1.100" in url


class TestEnsureActionApiForced:
    def test_reuses_healthy(self):
        from quodeq.dashboard._server import _ensure_action_api_forced
        probes = ApiProbes(api_healthy=lambda *_a: True, is_port_open=lambda *_a: True)
        url, proc = _ensure_action_api_forced("127.0.0.1", 5000, probes=probes)
        assert url == "http://127.0.0.1:5000"
        assert proc is None

    def test_raises_when_port_in_use_not_healthy(self):
        from quodeq.dashboard._server import _ensure_action_api_forced
        probes = ApiProbes(api_healthy=lambda *_a: False, is_port_open=lambda *_a: True)
        with pytest.raises(RuntimeError, match="Port 5000"):
            _ensure_action_api_forced("127.0.0.1", 5000, probes=probes)

    def test_spawns_when_port_free(self):
        from quodeq.dashboard._server import _ensure_action_api_forced
        probes = ApiProbes(
            is_port_open=lambda *_a: False,
            spawn=lambda *_a, **_k: ("http://127.0.0.1:5000", MagicMock()),
        )
        url, proc = _ensure_action_api_forced("127.0.0.1", 5000, probes=probes)
        assert url == "http://127.0.0.1:5000"

    def test_passes_static_and_eval_dirs(self):
        from quodeq.dashboard._server import _ensure_action_api_forced
        spawn = MagicMock(return_value=("http://127.0.0.1:5000", MagicMock()))
        probes = ApiProbes(is_port_open=lambda *_a: False, spawn=spawn)
        _ensure_action_api_forced(
            "127.0.0.1", 5000, static_dist=Path("/static"), evaluations_dir="/evals", probes=probes,
        )
        args = spawn.call_args
        assert args[0][1] == "http://127.0.0.1:5000"
