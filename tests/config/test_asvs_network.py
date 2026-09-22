from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quodeq.config._asvs_network import fetch_with_retry, _MAX_FETCH_BYTES


def test_fetch_with_retry_rejects_oversized_response():
    fake_response = MagicMock()
    fake_response.read.return_value = b"x" * (_MAX_FETCH_BYTES + 1)
    fake_response.__enter__ = lambda self: fake_response
    fake_response.__exit__ = lambda self, *a: False

    with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen, \
         patch("quodeq.config._asvs_network.time.sleep") as mock_sleep:
        with pytest.raises(ConnectionError, match="exceeds"):
            fetch_with_retry("https://example.com/asvs.json", max_retries=3)

    # An oversized response can't be fixed by retrying, so it must raise on
    # the first attempt instead of being caught and retried as a network error.
    mock_urlopen.assert_called_once()
    mock_sleep.assert_not_called()


def test_fetch_with_retry_returns_content_under_the_cap():
    fake_response = MagicMock()
    fake_response.read.return_value = b"small content"
    fake_response.__enter__ = lambda self: fake_response
    fake_response.__exit__ = lambda self, *a: False

    with patch("urllib.request.urlopen", return_value=fake_response), \
         patch("quodeq.config._asvs_network.validate_url_safe"):
        result = fetch_with_retry("https://example.com/asvs.json", max_retries=1)

    assert result == b"small content"
