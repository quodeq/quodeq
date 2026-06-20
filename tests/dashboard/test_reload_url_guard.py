"""Tests for the reload URL guard that restricts webview navigation to localhost."""
from __future__ import annotations

from unittest.mock import MagicMock

from quodeq.dashboard._webview_window import _is_safe_reload_url, _make_on_reload


# ---------------------------------------------------------------------------
# Unit tests for the pure guard function
# ---------------------------------------------------------------------------

class TestIsSafeReloadUrl:
    def test_localhost_http_allowed(self):
        assert _is_safe_reload_url("http://localhost:7863") is True

    def test_localhost_https_allowed(self):
        assert _is_safe_reload_url("https://localhost:7863") is True

    def test_127_0_0_1_http_allowed(self):
        assert _is_safe_reload_url("http://127.0.0.1:7863") is True

    def test_127_0_0_1_https_allowed(self):
        assert _is_safe_reload_url("https://127.0.0.1:7863") is True

    def test_ipv6_loopback_allowed(self):
        assert _is_safe_reload_url("http://[::1]:7863") is True

    def test_localhost_with_path_allowed(self):
        assert _is_safe_reload_url("http://localhost:7863/some/path") is True

    def test_remote_host_rejected(self):
        assert _is_safe_reload_url("http://evil.example.com/payload") is False

    def test_file_scheme_rejected(self):
        assert _is_safe_reload_url("file:///etc/passwd") is False

    def test_javascript_scheme_rejected(self):
        assert _is_safe_reload_url("javascript:alert(1)") is False

    def test_empty_string_rejected(self):
        assert _is_safe_reload_url("") is False

    def test_localhost_lookalike_rejected(self):
        # attacker-controlled domain that contains "localhost"
        assert _is_safe_reload_url("http://evillocalhost.com/") is False

    def test_127_0_0_1_lookalike_with_extra_octet_rejected(self):
        assert _is_safe_reload_url("http://127.0.0.1.evil.com/") is False

    def test_no_scheme_rejected(self):
        assert _is_safe_reload_url("localhost:7863") is False


# ---------------------------------------------------------------------------
# Integration: the _on_reload closure must use the guard
# ---------------------------------------------------------------------------

class TestOnReloadGuard:
    """Verify that the live _on_reload wiring in main() uses the guard.

    Uses the real ``_make_on_reload`` factory (same code path as ``main()``)
    so that removing the guard call from ``main()`` would cause these tests
    to fail.
    """

    def _make_handler(self) -> tuple["Callable[[str], None]", MagicMock]:
        window = MagicMock()
        return _make_on_reload(window), window

    def test_safe_url_navigates(self):
        on_reload, window = self._make_handler()
        on_reload("http://127.0.0.1:7863")
        window.load_url.assert_called_once_with("http://127.0.0.1:7863")

    def test_unsafe_url_does_not_navigate(self):
        on_reload, window = self._make_handler()
        on_reload("http://evil.example.com/steal-tokens")
        window.load_url.assert_not_called()

    def test_file_url_does_not_navigate(self):
        on_reload, window = self._make_handler()
        on_reload("file:///etc/passwd")
        window.load_url.assert_not_called()
