"""Tests for quodeq.update.download.download_file: retry on transient failures."""
from __future__ import annotations

import httpx
import pytest

from quodeq.update.download import download_file


class _FakeResponse:
    def __init__(self, status=200, body=b""):
        self.status_code = status
        self.headers: dict = {}
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com/f")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def iter_bytes(self):
        yield self._body


class _FakeStream:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self._resp

    def __exit__(self, *args):
        return False


def test_download_file_retries_transport_errors_then_succeeds(tmp_path, monkeypatch):
    dest = tmp_path / "out.bin"
    calls = [
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        _FakeStream(_FakeResponse(body=b"abc")),
    ]

    def fake_stream(method, url, **kwargs):
        item = calls.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("quodeq.update.download.httpx.stream", fake_stream)
    download_file("https://example.com/f", dest, lambda done, total: None, sleep=lambda s: None)
    assert dest.read_bytes() == b"abc"


def test_download_file_reraises_after_exhausting_attempts(tmp_path, monkeypatch):
    dest = tmp_path / "out.bin"
    errors = [httpx.ConnectError("refused") for _ in range(4)]
    calls = {"n": 0}

    def fake_stream(method, url, **kwargs):
        calls["n"] += 1
        raise errors[calls["n"] - 1]

    monkeypatch.setattr("quodeq.update.download.httpx.stream", fake_stream)
    with pytest.raises(httpx.ConnectError):
        download_file("https://example.com/f", dest, lambda done, total: None, sleep=lambda s: None)
    # attempts defaults to 3: the 4th queued error is never consumed.
    assert calls["n"] == 3


def test_download_file_does_not_retry_a_client_error(tmp_path, monkeypatch):
    dest = tmp_path / "out.bin"
    calls = {"n": 0}

    def fake_stream(method, url, **kwargs):
        calls["n"] += 1
        return _FakeStream(_FakeResponse(status=404))

    monkeypatch.setattr("quodeq.update.download.httpx.stream", fake_stream)
    with pytest.raises(httpx.HTTPStatusError):
        download_file("https://example.com/f", dest, lambda done, total: None, sleep=lambda s: None)
    assert calls["n"] == 1
