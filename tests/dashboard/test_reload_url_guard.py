"""Tests for the reload URL guard that restricts webview navigation to localhost."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from quodeq.dashboard._webview_window import (
    _download_via_dialog,
    _is_safe_reload_url,
    _make_on_reload,
)


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

    def test_focus_reloads_the_window_own_url(self):
        """The empty-URL focus case reloads in place and never navigates away."""
        on_reload, window = self._make_handler()
        window.get_current_url.return_value = "http://127.0.0.1:7863/#/overview"
        on_reload("")
        window.load_url.assert_called_once_with("http://127.0.0.1:7863/#/overview")

    def test_focus_still_raises_when_the_url_is_unavailable(self):
        on_reload, window = self._make_handler()
        window.get_current_url.side_effect = RuntimeError("no backend yet")
        on_reload("")
        window.load_url.assert_not_called()
        assert window.on_top is False  # raised, then released

    def test_focus_will_not_reload_an_unsafe_current_url(self):
        """Defence in depth: even self-reported URLs go through the guard."""
        on_reload, window = self._make_handler()
        window.get_current_url.return_value = "http://evil.example.com/"
        on_reload("")
        window.load_url.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests for _download_via_dialog URL validation
# ---------------------------------------------------------------------------


class TestDownloadViaDialogUrlValidation:
    """Verify that _download_via_dialog validates joined URLs against the allowlist."""

    def _make_window_and_dialog(self, save_path: str) -> MagicMock:
        """Create a mock window with a configured save dialog."""
        window = MagicMock()
        window.create_file_dialog.return_value = save_path
        return window

    def test_download_normal_relative_path_accepted(self, tmp_path):
        """A normal relative path that joins to a safe URL should succeed."""
        window = self._make_window_and_dialog(str(tmp_path / "output.txt"))
        base_url = "http://127.0.0.1:7863"
        path = "/api/export/results"

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"test data"
            mock_response.__enter__.return_value = mock_response
            mock_response.__exit__.return_value = False
            mock_urlopen.return_value = mock_response

            result = _download_via_dialog(window, base_url, path, "output.txt")

        assert result is True
        mock_urlopen.assert_called_once()
        called_url = mock_urlopen.call_args[0][0]
        assert called_url == "http://127.0.0.1:7863/api/export/results"

    def test_download_path_with_network_scheme_rejected(self, tmp_path):
        """A path starting with // (network scheme) should be rejected."""
        window = self._make_window_and_dialog(str(tmp_path / "output.txt"))
        base_url = "http://127.0.0.1:7863"
        path = "//evil.example.com/steal-data"

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = _download_via_dialog(window, base_url, path, "output.txt")

        assert result is False
        mock_urlopen.assert_not_called()

    def test_download_path_with_absolute_scheme_rejected(self, tmp_path):
        """A path with an absolute scheme should be rejected."""
        window = self._make_window_and_dialog(str(tmp_path / "output.txt"))
        base_url = "http://127.0.0.1:7863"
        path = "https://evil.example.com/steal-data"

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = _download_via_dialog(window, base_url, path, "output.txt")

        assert result is False
        mock_urlopen.assert_not_called()

    def test_download_file_scheme_rejected(self, tmp_path):
        """A file:// scheme in the path should be rejected."""
        window = self._make_window_and_dialog(str(tmp_path / "output.txt"))
        base_url = "http://127.0.0.1:7863/api/"
        path = "file:///etc/passwd"

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = _download_via_dialog(window, base_url, path, "output.txt")

        assert result is False
        mock_urlopen.assert_not_called()

    def test_download_localhost_path_accepted(self, tmp_path):
        """A relative path joining to localhost should succeed."""
        window = self._make_window_and_dialog(str(tmp_path / "output.txt"))
        base_url = "http://localhost:7863"
        path = "/api/results.json"

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"test data"
            mock_response.__enter__.return_value = mock_response
            mock_response.__exit__.return_value = False
            mock_urlopen.return_value = mock_response

            result = _download_via_dialog(window, base_url, path, "output.json")

        assert result is True
        mock_urlopen.assert_called_once()
