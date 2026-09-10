"""Cluster 13 (R-FT-7) — except narrowing for two `_webview_window_native_ops`
call sites:

* ``_fetch_running_evaluation`` (urllib fetch + ``json.loads``) — narrowed
  from bare ``Exception`` to ``(OSError, ValueError)``.
* ``_download_via_dialog`` (urllib fetch + file write) — the tuple
  ``(OSError, Exception)`` was a no-op (``OSError`` is already an
  ``Exception`` subclass); narrowed to plain ``OSError``, matching
  ``_save_via_dialog``'s equivalent file-write catch immediately above it.
"""
from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from quodeq.dashboard._webview_window import (
    _download_via_dialog,
    _fetch_running_evaluation,
)


# ---------------------------------------------------------------------------
# _fetch_running_evaluation
# ---------------------------------------------------------------------------


class TestFetchRunningEvaluationExceptNarrowing:
    def test_url_error_is_caught_and_returns_none(self):
        """A realistic network failure (connection refused) is swallowed."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            assert _fetch_running_evaluation("http://127.0.0.1:7863") is None

    def test_malformed_json_is_caught_and_returns_none(self):
        """A realistic response-shape failure (non-JSON body) is swallowed."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert _fetch_running_evaluation("http://127.0.0.1:7863") is None

    def test_out_of_scope_error_propagates(self):
        """R-FT-7 — an error outside (OSError, ValueError) (e.g. a
        programming bug) must now propagate instead of being swallowed."""
        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                _fetch_running_evaluation("http://127.0.0.1:7863")


# ---------------------------------------------------------------------------
# _download_via_dialog
# ---------------------------------------------------------------------------


class TestDownloadViaDialogExceptNarrowing:
    def _window(self, save_path: str) -> MagicMock:
        window = MagicMock()
        window.create_file_dialog.return_value = save_path
        return window

    def test_write_failure_is_caught_and_returns_false(self, tmp_path):
        """A realistic write failure (target directory doesn't exist) is
        swallowed and reported as False, matching _save_via_dialog."""
        window = self._window(str(tmp_path / "does-not-exist" / "output.txt"))
        mock_response = MagicMock()
        mock_response.read.return_value = b"data"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = _download_via_dialog(
                window, "http://127.0.0.1:7863", "/api/export", "output.txt",
            )

        assert result is False

    def test_url_error_is_caught_and_returns_false(self, tmp_path):
        window = self._window(str(tmp_path / "output.txt"))

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = _download_via_dialog(
                window, "http://127.0.0.1:7863", "/api/export", "output.txt",
            )

        assert result is False

    def test_out_of_scope_error_propagates(self, tmp_path):
        """R-FT-7 — the old `except (OSError, Exception)` was a no-op tuple,
        literally equivalent to `except Exception`. Now that it's narrowed
        to plain OSError, anything else (e.g. a programming bug) must
        propagate instead of being swallowed."""
        window = self._window(str(tmp_path / "output.txt"))

        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                _download_via_dialog(
                    window, "http://127.0.0.1:7863", "/api/export", "output.txt",
                )
