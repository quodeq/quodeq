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
