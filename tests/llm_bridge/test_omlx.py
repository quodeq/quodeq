"""Tests for omlx integration in llm_bridge."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from quodeq.llm_bridge._omlx import (
    _normalize_base,
    _read_omlx_api_key,
    get_omlx_status,
)


class TestReadOmlxApiKey:
    def test_returns_env_var_when_set(self):
        with patch.dict("os.environ", {"OMLX_API_KEY": "env-key"}):
            result = _read_omlx_api_key()
        assert result == "env-key"

    def test_no_warning_when_env_var_set(self):
        with patch.dict("os.environ", {"OMLX_API_KEY": "env-key"}), \
             patch("quodeq.llm_bridge._omlx._log") as mock_log:
            _read_omlx_api_key()
        mock_log.warning.assert_not_called()

    def test_warning_when_file_fallback_with_key(self, tmp_path):
        omlx_dir = tmp_path / ".omlx"
        omlx_dir.mkdir()
        settings_file = omlx_dir / "settings.json"
        settings_file.write_text(json.dumps({"auth": {"api_key": "file-key"}}))

        with patch.dict("os.environ", {"OMLX_API_KEY": ""}, clear=True), \
             patch("quodeq.llm_bridge._omlx.Path") as mock_path_cls, \
             patch("quodeq.llm_bridge._omlx._log") as mock_log:
            mock_path_cls.home.return_value = tmp_path

            result = _read_omlx_api_key()

        assert result == "file-key"
        mock_log.warning.assert_called_once()
        warning_msg = mock_log.warning.call_args[0][0]
        assert "cleartext" in warning_msg
        assert "~/.omlx/settings.json" in warning_msg
        assert "OMLX_API_KEY" in warning_msg

    def test_no_warning_when_file_fallback_no_key(self, tmp_path):
        omlx_dir = tmp_path / ".omlx"
        omlx_dir.mkdir()
        settings_file = omlx_dir / "settings.json"
        settings_file.write_text(json.dumps({"auth": {}}))

        with patch.dict("os.environ", {"OMLX_API_KEY": ""}, clear=True), \
             patch("quodeq.llm_bridge._omlx.Path") as mock_path_cls, \
             patch("quodeq.llm_bridge._omlx._log") as mock_log:
            mock_path_cls.home.return_value = tmp_path

            result = _read_omlx_api_key()

        assert result == ""
        mock_log.warning.assert_not_called()

    def test_no_warning_when_file_not_found(self, tmp_path):
        with patch.dict("os.environ", {"OMLX_API_KEY": ""}, clear=True), \
             patch("quodeq.llm_bridge._omlx.Path") as mock_path_cls, \
             patch("quodeq.llm_bridge._omlx._log") as mock_log:
            mock_path_cls.home.return_value = tmp_path

            result = _read_omlx_api_key()

        assert result == ""
        mock_log.warning.assert_not_called()

    def test_no_warning_when_invalid_json(self, tmp_path):
        omlx_dir = tmp_path / ".omlx"
        omlx_dir.mkdir()
        settings_file = omlx_dir / "settings.json"
        settings_file.write_text("invalid json")

        with patch.dict("os.environ", {"OMLX_API_KEY": ""}, clear=True), \
             patch("quodeq.llm_bridge._omlx.Path") as mock_path_cls, \
             patch("quodeq.llm_bridge._omlx._log") as mock_log:
            mock_path_cls.home.return_value = tmp_path

            result = _read_omlx_api_key()

        assert result == ""
        mock_log.warning.assert_not_called()


class TestNormalizeBase:
    def test_strips_v1_suffix(self):
        assert _normalize_base("http://localhost:8000/v1") == "http://localhost:8000"

    def test_strips_trailing_slash(self):
        assert _normalize_base("http://localhost:8000/") == "http://localhost:8000"

    def test_leaves_root_alone(self):
        assert _normalize_base("http://localhost:8000") == "http://localhost:8000"


class TestGetOmlxStatus:
    def test_running(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status":"ok"}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp):
            result = get_omlx_status("http://localhost:8000")

        assert result["running"] is True
        assert result["status"] == "ok"
        assert "8000" in result["address"]

    def test_running_with_v1_suffix(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            get_omlx_status("http://localhost:8000/v1")

        called_url = mock_open.call_args[0][0].full_url
        assert called_url.endswith("/health")
        assert "/v1/health" not in called_url

    def test_not_running(self):
        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", side_effect=ConnectionRefusedError):
            result = get_omlx_status()

        assert result["running"] is False
        assert "error" in result

    def test_non_object_body_still_reports_running(self):
        """A health body that is valid JSON but not an object must not raise;
        the server responded, so it is running with the default status."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'["ok"]'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp):
            result = get_omlx_status("http://localhost:8000")

        assert result["running"] is True
        assert result["status"] == "ok"

    def test_malformed_body_reports_not_running(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>bad gateway</html>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("quodeq.llm_bridge._omlx.urllib.request.urlopen", return_value=mock_resp):
            result = get_omlx_status("http://localhost:8000")

        assert result["running"] is False
