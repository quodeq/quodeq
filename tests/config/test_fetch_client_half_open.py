"""FetchClient circuit half-open: one probe after the cooldown closes or re-opens it."""
from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

from quodeq.config._fetch_client_class import FetchClient


def _resp(body: bytes):
    m = MagicMock()
    m.read.return_value = body
    m.__enter__ = MagicMock(return_value=m)
    m.__exit__ = MagicMock(return_value=False)
    return m


class TestCircuitHalfOpen:
    """An open circuit lets one probe through once the cooldown has passed."""

    _URL = "https://example.com"

    @staticmethod
    def _tripped_client(monkeypatch, clock: list[float]) -> FetchClient:
        monkeypatch.setattr("quodeq.config._fetch_client_class.time.monotonic", lambda: clock[0])
        c = FetchClient(allow_private=True, env={
            "QUODEQ_CIRCUIT_THRESHOLD": "2", "QUODEQ_CIRCUIT_RESET_S": "60", "QUODEQ_MAX_RETRIES": "0",
        })
        for _ in range(2):
            c._record_failure(Exception("fail"))
        return c

    def test_reset_from_injected_env_and_default(self):
        assert FetchClient(env={"QUODEQ_CIRCUIT_RESET_S": "5"})._CIRCUIT_RESET_S == 5.0
        assert FetchClient(env={})._CIRCUIT_RESET_S == 60.0

    def test_circuit_half_opens_after_cooldown_and_closes_on_success(self, monkeypatch):
        clock = [1000.0]
        c = self._tripped_client(monkeypatch, clock)
        opener = MagicMock(side_effect=lambda *_a, **_k: _resp(b"body"))
        with patch("urllib.request.OpenerDirector.open", opener):
            clock[0] = 1059.0
            assert c.fetch(self._URL) is None
            assert opener.call_count == 0
            clock[0] = 1060.0
            assert c.fetch(self._URL) == "body"
            assert opener.call_count == 1
            assert c.fetch(self._URL) == "body"
            assert opener.call_count == 2

    def test_half_open_probe_failure_reopens_with_new_cooldown(self, monkeypatch):
        clock = [1000.0]
        c = self._tripped_client(monkeypatch, clock)
        opener = MagicMock(side_effect=urllib.error.URLError("net error"))
        with patch("urllib.request.OpenerDirector.open", opener), patch("time.sleep"):
            clock[0] = 1061.0
            assert c.fetch(self._URL) is None
            assert opener.call_count == 1
            assert c.fetch(self._URL) is None
            clock[0] = 1120.0
            assert c.fetch(self._URL) is None
            assert opener.call_count == 1

    def test_concurrent_call_during_probe_sees_circuit_open(self, monkeypatch):
        clock = [1000.0]
        c = self._tripped_client(monkeypatch, clock)
        clock[0] = 1060.0
        assert c._is_circuit_open() is False
        assert c._is_circuit_open() is True
