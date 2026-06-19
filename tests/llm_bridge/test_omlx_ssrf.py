"""SSRF guard tests for omlx integration.

These tests verify that unsafe base_url values (cloud metadata endpoints,
private-range IPs, non-HTTP schemes) are rejected before urlopen is called,
while a legitimate localhost base_url still reaches urlopen normally.
"""
from __future__ import annotations

import pytest

from quodeq.llm_bridge import _omlx


_UNSAFE_URLS = [
    "http://169.254.169.254/latest/meta-data/",   # AWS IMDSv1
    "http://169.254.169.254/",                     # link-local / GCP metadata
    "http://10.0.0.1/",                            # RFC1918 private range
    "http://192.168.1.1/",                         # RFC1918 private range
    "file:///etc/passwd",                          # non-HTTP scheme
]


@pytest.mark.parametrize("bad_url", _UNSAFE_URLS)
def test_get_omlx_status_rejects_unsafe_base_url(bad_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(_omlx.urllib.request, "urlopen", lambda *a, **k: calls.append(1))
    result = _omlx.get_omlx_status(base_url=bad_url)
    assert calls == [], f"urlopen should not be called for unsafe URL {bad_url!r}"
    assert result["running"] is False
    assert "error" in result


@pytest.mark.parametrize("bad_url", _UNSAFE_URLS)
def test_list_omlx_models_rejects_unsafe_base_url(bad_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(_omlx.urllib.request, "urlopen", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(_omlx, "_list_model_dirs", lambda: [])
    result = _omlx.list_omlx_models(base_url=bad_url)
    assert calls == [], f"urlopen should not be called for unsafe URL {bad_url!r}"
    # Falls back to _list_model_dirs, which returns []
    assert result == []


def test_get_omlx_status_allows_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """A localhost base_url must still reach urlopen (legitimate omlx default)."""
    calls: list[object] = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        raise ConnectionRefusedError("nobody home")

    monkeypatch.setattr(_omlx.urllib.request, "urlopen", fake_urlopen)
    result = _omlx.get_omlx_status(base_url="http://localhost:8000")
    assert len(calls) == 1, "urlopen should have been called for localhost"
    assert result["running"] is False  # connection refused, but guard passed


def test_list_omlx_models_allows_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """A localhost base_url must still reach urlopen (legitimate omlx default)."""
    calls: list[object] = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        raise ConnectionRefusedError("nobody home")

    monkeypatch.setattr(_omlx.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(_omlx, "_list_model_dirs", lambda: [])
    _omlx.list_omlx_models(base_url="http://localhost:8000")
    assert len(calls) == 1, "urlopen should have been called for localhost"
