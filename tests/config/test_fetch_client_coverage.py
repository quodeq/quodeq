"""Tests for quodeq.config._fetch_client_class — FetchClient with circuit breaker and retry."""
from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from quodeq.config._fetch_client_class import FetchClient


class TestFetchClientInit:
    def test_default_timeout(self):
        c = FetchClient()
        assert c._timeout == 15

    def test_custom_timeout(self):
        c = FetchClient(timeout_s=30)
        assert c._timeout == 30

    def test_allow_private_from_env(self):
        c = FetchClient(env={"QUODEQ_ALLOW_PRIVATE_URLS": "1"})
        assert c._allow_private is True

    def test_allow_private_not_set(self):
        c = FetchClient(env={})
        assert c._allow_private is False

    def test_allow_private_explicit(self):
        c = FetchClient(allow_private=True)
        assert c._allow_private is True


class TestCircuitBreaker:
    def test_circuit_not_open_initially(self):
        c = FetchClient()
        assert c._is_circuit_open() is False

    def test_circuit_opens_after_threshold(self):
        c = FetchClient()
        for _ in range(5):
            c._record_failure(Exception("fail"))
        assert c._is_circuit_open() is True

    def test_circuit_resets_on_success(self):
        c = FetchClient()
        for _ in range(4):
            c._record_failure(Exception("fail"))
        c._record_success()
        assert c._is_circuit_open() is False

    def test_circuit_open_returns_none(self):
        c = FetchClient()
        for _ in range(5):
            c._record_failure(Exception("fail"))
        assert c.fetch("https://example.com") is None


class TestFetchValidation:
    def test_blocks_non_http_scheme(self):
        c = FetchClient()
        assert c.fetch("ftp://example.com") is None

    def test_blocks_private_address(self):
        c = FetchClient(allow_private=False, env={})
        result = c.fetch("http://127.0.0.1/test")
        # Should be blocked (private address)
        assert result is None

    def test_allows_private_when_enabled(self):
        c = FetchClient(allow_private=True)
        # Will fail on network, but should not be blocked by the private check
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("test")):
            result = c.fetch("http://127.0.0.1/test")
            assert result is None  # fails on network, not on validation


class TestFetchClientConfigInjection:
    def test_circuit_threshold_from_injected_env(self):
        c = FetchClient(env={"QUODEQ_CIRCUIT_THRESHOLD": "3"})
        assert c._CIRCUIT_THRESHOLD == 3

    def test_max_retries_from_injected_env(self):
        c = FetchClient(env={"QUODEQ_MAX_RETRIES": "5"})
        assert c._MAX_RETRIES == 5

    def test_retry_backoff_from_injected_env(self):
        c = FetchClient(env={"QUODEQ_RETRY_BACKOFF_S": "1.5"})
        assert c._RETRY_BACKOFF_S == 1.5

    def test_defaults_when_keys_absent(self):
        c = FetchClient(env={})
        assert c._CIRCUIT_THRESHOLD == 5
        assert c._MAX_RETRIES == 2
        assert c._RETRY_BACKOFF_S == 0.5


class TestFetchRetry:
    def test_successful_fetch(self):
        c = FetchClient(allow_private=True)
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"hello world"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = c.fetch("https://example.com")
            assert result == "hello world"

    def test_retries_on_failure(self):
        c = FetchClient(allow_private=True)
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("net error")), \
             patch("time.sleep"):
            result = c.fetch("https://example.com")
            assert result is None

    def test_records_failure_after_retries(self):
        c = FetchClient(allow_private=True)
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("net error")), \
             patch("time.sleep"):
            c.fetch("https://example.com")
            assert c._failures == 1


class TestFetchResponseSizeCap:
    """A fetch must be bounded in BYTES, not only in seconds.

    ``timeout`` bounds how long the transfer may run; on a fast link a hostile
    or broken endpoint still streams enough in that window to exhaust memory.
    These pin the byte cap so the guard cannot be silently dropped.
    """

    @staticmethod
    def _resp(body: bytes):
        m = MagicMock()
        m.read.return_value = body
        m.__enter__ = MagicMock(return_value=m)
        m.__exit__ = MagicMock(return_value=False)
        return m

    def test_default_cap(self):
        assert FetchClient(env={})._MAX_BODY_BYTES == 10 * 1024 * 1024

    def test_cap_from_injected_env(self):
        assert FetchClient(env={"QUODEQ_MAX_RESPONSE_BYTES": "2048"})._MAX_BODY_BYTES == 2048

    def test_read_is_always_bounded(self):
        # The regression guard: an unbounded r.read() would pass every other
        # test in this class while still being the bug.
        c = FetchClient(allow_private=True, env={})
        resp = self._resp(b"ok")
        with patch("urllib.request.urlopen", return_value=resp):
            c.fetch("https://example.com")
        args, _kwargs = resp.read.call_args
        assert args, "r.read() called with no size limit"
        assert args[0] == c._MAX_BODY_BYTES + 1

    def test_body_at_cap_is_returned(self):
        c = FetchClient(allow_private=True, env={"QUODEQ_MAX_RESPONSE_BYTES": "16"})
        with patch("urllib.request.urlopen", return_value=self._resp(b"x" * 16)):
            assert c.fetch("https://example.com") == "x" * 16

    def test_body_over_cap_is_rejected(self):
        c = FetchClient(allow_private=True, env={"QUODEQ_MAX_RESPONSE_BYTES": "16"})
        with patch("urllib.request.urlopen", return_value=self._resp(b"x" * 17)):
            assert c.fetch("https://example.com") is None

    def test_oversize_counts_as_failure(self):
        c = FetchClient(allow_private=True, env={"QUODEQ_MAX_RESPONSE_BYTES": "4"})
        with patch("urllib.request.urlopen", return_value=self._resp(b"toolong")):
            c.fetch("https://example.com")
        assert c._failures == 1

    def test_oversize_does_not_retry(self):
        # Body size is a deterministic property of the endpoint; retrying only
        # re-downloads the cap. One attempt, then give up.
        c = FetchClient(allow_private=True, env={"QUODEQ_MAX_RESPONSE_BYTES": "4"})
        opener = MagicMock(return_value=self._resp(b"toolong"))
        with patch("urllib.request.urlopen", opener), patch("time.sleep"):
            c.fetch("https://example.com")
        assert opener.call_count == 1
