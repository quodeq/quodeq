"""Except narrowing for two `_webview_window_native_ops`
call sites (R-FT-7):

* ``fetch_running_evaluation`` (urllib fetch + ``json.loads``) — narrowed
  from bare ``Exception`` to ``(OSError, ValueError)``.
* ``download_via_dialog`` (urllib fetch + file write) — the tuple
  ``(OSError, Exception)`` was a no-op (``OSError`` is already an
  ``Exception`` subclass); narrowed to plain ``OSError``, matching
  ``save_via_dialog``'s equivalent file-write catch immediately above it.

``save_via_dialog``'s own warning-log addition is covered in
tests/dashboard/test_native_chrome_close_choice.py (via the already-imported
``ww`` module alias, to avoid a new named private import here).
"""
from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from quodeq.dashboard._webview_window import (
    download_via_dialog,
    fetch_running_evaluation,
)


# ---------------------------------------------------------------------------
# fetch_running_evaluation
# ---------------------------------------------------------------------------


class TestFetchRunningEvaluationExceptNarrowing:
    def test_url_error_is_caught_and_returns_none(self):
        """A realistic network failure (connection refused) is swallowed."""
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            assert fetch_running_evaluation("http://127.0.0.1:7863") is None

    def test_malformed_json_is_caught_and_returns_none(self):
        """A realistic response-shape failure (non-JSON body) is swallowed."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert fetch_running_evaluation("http://127.0.0.1:7863") is None

    def test_out_of_scope_error_propagates(self):
        """R-FT-7 — an error outside (OSError, ValueError) (e.g. a
        programming bug) must now propagate instead of being swallowed."""
        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                fetch_running_evaluation("http://127.0.0.1:7863")


# ---------------------------------------------------------------------------
# download_via_dialog
# ---------------------------------------------------------------------------


class TestDownloadViaDialogExceptNarrowing:
    def _window(self, save_path: str) -> MagicMock:
        window = MagicMock()
        window.create_file_dialog.return_value = save_path
        return window

    def test_write_failure_is_caught_and_returns_false(self, tmp_path):
        """A realistic write failure (target directory doesn't exist) is
        swallowed and reported as False, matching save_via_dialog."""
        window = self._window(str(tmp_path / "does-not-exist" / "output.txt"))
        mock_response = MagicMock()
        mock_response.read.return_value = b"data"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = download_via_dialog(
                window, "http://127.0.0.1:7863", "/api/export", "output.txt",
            )

        assert result is False

    def test_url_error_is_caught_and_returns_false(self, tmp_path):
        window = self._window(str(tmp_path / "output.txt"))

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = download_via_dialog(
                window, "http://127.0.0.1:7863", "/api/export", "output.txt",
            )

        assert result is False

    def test_out_of_scope_error_propagates(self, tmp_path):
        """R-FT-7 — the old `except (OSError, Exception)` was a no-op tuple,
        literally equivalent to `except Exception`. Now that it's narrowed
        to the transport family, anything else (e.g. a programming bug) must
        propagate instead of being swallowed."""
        window = self._window(str(tmp_path / "output.txt"))

        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                download_via_dialog(
                    window, "http://127.0.0.1:7863", "/api/export", "output.txt",
                )

    # Two realistic transport failures sat outside plain
    # OSError and escaped into the pywebview js_api bridge as an unhandled
    # error instead of reporting "download failed".

    def test_truncated_response_is_caught_and_returns_false(self, tmp_path):
        import http.client

        window = self._window(str(tmp_path / "output.txt"))
        mock_response = MagicMock()
        mock_response.read.side_effect = http.client.IncompleteRead(b"partial")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = download_via_dialog(
                window, "http://127.0.0.1:7863", "/api/export", "output.txt",
            )

        assert result is False
        assert not (tmp_path / "output.txt").exists()

    def test_malformed_url_is_caught_and_returns_false(self, tmp_path):
        # urllib raises ValueError("unknown url type") for a URL it cannot parse.
        window = self._window(str(tmp_path / "output.txt"))

        with patch("urllib.request.urlopen", side_effect=ValueError("unknown url type")):
            result = download_via_dialog(
                window, "http://127.0.0.1:7863", "/api/export", "output.txt",
            )

        assert result is False

    def test_download_streams_in_chunks(self, tmp_path):
        import io

        target = tmp_path / "output.bin"
        body = io.BytesIO(b"x" * 300_000)
        sizes: list[int] = []
        mock_response = MagicMock()
        mock_response.read.side_effect = lambda n=-1: (sizes.append(n), body.read(n))[1]
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = download_via_dialog(
                self._window(str(target)), "http://127.0.0.1:7863", "/api/export", "output.bin",
            )

        assert result is True
        assert target.read_bytes() == b"x" * 300_000
        # never an unbounded read(); several chunks (64 KiB on POSIX, 1 MiB on Windows)
        assert len(sizes) >= 2 and all(n > 0 for n in sizes)
        assert not (tmp_path / "output.bin.part").exists()

    def test_a_truncated_download_keeps_the_existing_file(self, tmp_path):
        import http.client

        target = tmp_path / "output.txt"
        target.write_text("keep me")
        mock_response = MagicMock()
        mock_response.read.side_effect = http.client.IncompleteRead(b"partial")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = download_via_dialog(
                self._window(str(target)), "http://127.0.0.1:7863", "/api/export", "output.txt",
            )

        assert result is False
        assert target.read_text() == "keep me"
        assert not (tmp_path / "output.txt.part").exists()
        # no temp file left behind either: the directory holds only the target
        assert [p.name for p in tmp_path.iterdir()] == ["output.txt"]

    def test_a_pre_existing_partial_file_survives_a_failed_request(self, tmp_path):
        """R-M5: a request that fails before any temp file is created must
        not delete an unrelated file the user already has sitting at the
        `<target>.part` path (cleanup must only ever remove a temp file
        this call itself created)."""
        target = tmp_path / "output.txt"
        stray_partial = tmp_path / "output.txt.part"
        stray_partial.write_text("not ours")

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = download_via_dialog(
                self._window(str(target)), "http://127.0.0.1:7863", "/api/export", "output.txt",
            )

        assert result is False
        assert stray_partial.read_text() == "not ours"
        assert not target.exists()
