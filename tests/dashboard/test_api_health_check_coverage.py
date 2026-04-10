"""Tests for quodeq.dashboard._api_health_check — health checking and polling."""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest


class TestActionApiHealthy:
    def test_healthy(self):
        from quodeq.dashboard._api_health_check import action_api_healthy
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert action_api_healthy("http://localhost:5000") is True

    def test_unhealthy_status(self):
        from quodeq.dashboard._api_health_check import action_api_healthy
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert action_api_healthy("http://localhost:5000") is False

    def test_unhealthy_payload(self):
        from quodeq.dashboard._api_health_check import action_api_healthy
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"ok": False}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert action_api_healthy("http://localhost:5000") is False

    def test_connection_error(self):
        from quodeq.dashboard._api_health_check import action_api_healthy
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            assert action_api_healthy("http://localhost:5000") is False

    def test_json_error(self):
        from quodeq.dashboard._api_health_check import action_api_healthy
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert action_api_healthy("http://localhost:5000") is False


class TestWaitForActionApi:
    def test_already_healthy(self):
        from quodeq.dashboard._api_health_check import wait_for_action_api
        with patch("quodeq.dashboard._api_health_check.action_api_healthy", return_value=True):
            wait_for_action_api("http://localhost:5000")  # should not raise

    def test_timeout(self):
        from quodeq.dashboard._api_health_check import wait_for_action_api
        with patch("quodeq.dashboard._api_health_check.action_api_healthy", return_value=False), \
             patch("time.sleep"):
            with pytest.raises(TimeoutError):
                wait_for_action_api("http://localhost:5000", timeout_s=0.01)

    def test_becomes_healthy(self):
        from quodeq.dashboard._api_health_check import wait_for_action_api
        calls = [False, False, True]
        with patch("quodeq.dashboard._api_health_check.action_api_healthy", side_effect=calls), \
             patch("time.sleep"):
            wait_for_action_api("http://localhost:5000", timeout_s=10)
