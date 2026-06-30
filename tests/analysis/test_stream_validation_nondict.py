"""#176 — get_mcp_status must not raise when json.loads returns a non-dict."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import mock_open, patch


class TestGetMcpStatusNonDict:
    def _write_stream(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "stream.json"
        p.write_text(content, encoding="utf-8")
        return p

    def test_list_payload_returns_none(self, tmp_path: Path) -> None:
        from quodeq.analysis.stream.validation import get_mcp_status
        p = self._write_stream(tmp_path, json.dumps([1, 2, 3]) + "\n")
        result = get_mcp_status(p)
        assert result is None

    def test_string_payload_returns_none(self, tmp_path: Path) -> None:
        from quodeq.analysis.stream.validation import get_mcp_status
        p = self._write_stream(tmp_path, '"just a string"\n')
        result = get_mcp_status(p)
        assert result is None

    def test_null_payload_returns_none(self, tmp_path: Path) -> None:
        from quodeq.analysis.stream.validation import get_mcp_status
        p = self._write_stream(tmp_path, "null\n")
        result = get_mcp_status(p)
        assert result is None

    def test_valid_dict_still_works(self, tmp_path: Path) -> None:
        from quodeq.analysis.stream.validation import get_mcp_status
        payload = {"mcp_servers": [{"name": "findings", "status": "ok"}]}
        p = self._write_stream(tmp_path, json.dumps(payload) + "\n")
        result = get_mcp_status(p)
        assert result == "ok"

    def test_non_dict_server_element_skipped(self, tmp_path: Path) -> None:
        """A non-dict element in mcp_servers must be skipped, not crash."""
        from quodeq.analysis.stream.validation import get_mcp_status
        payload = {"mcp_servers": ["garbage", 42, {"name": "findings", "status": "ok"}]}
        p = self._write_stream(tmp_path, json.dumps(payload) + "\n")
        assert get_mcp_status(p) == "ok"

    def test_non_list_mcp_servers_returns_none(self, tmp_path: Path) -> None:
        from quodeq.analysis.stream.validation import get_mcp_status
        p = self._write_stream(tmp_path, json.dumps({"mcp_servers": "x"}) + "\n")
        assert get_mcp_status(p) is None


class TestIsStreamValidNonDictLine:
    def test_non_dict_line_is_not_an_error_event(self, tmp_path: Path) -> None:
        """A valid-JSON line that is a list/scalar must not crash
        _is_error_event; the stream is treated as valid (no error event)."""
        from quodeq.analysis.stream.validation import is_stream_valid
        p = tmp_path / "stream.json"
        p.write_text(json.dumps([1, 2, 3]) + "\n", encoding="utf-8")
        assert is_stream_valid(p) is True

    def test_error_event_still_detected(self, tmp_path: Path) -> None:
        from quodeq.analysis.stream.validation import is_stream_valid
        p = tmp_path / "stream.json"
        p.write_text(json.dumps({"type": "result", "is_error": True}) + "\n", encoding="utf-8")
        assert is_stream_valid(p) is False
