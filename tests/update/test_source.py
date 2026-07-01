from unittest.mock import MagicMock, patch

import httpx

from quodeq.update.source import LatestInfo, fetch_latest

_GH_RELEASE = {
    "tag_name": "v1.5.0",
    "html_url": "https://github.com/quodeq/quodeq/releases/tag/v1.5.0",
    "body": "Routine bug fixes.",
    "labels": [],
    "assets": [
        {"name": "Quodeq-1.5.0-macOS.dmg", "browser_download_url": "https://example.com/Quodeq-1.5.0-macOS.dmg"},
    ],
}


def _resp(status=200, payload=None, etag='"abc"'):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload or {}
    r.headers = {"ETag": etag} if etag else {}
    return r


def test_frozen_reads_github() -> None:
    with patch("quodeq.update.source.httpx.get", return_value=_resp(payload=_GH_RELEASE)):
        info = fetch_latest("frozen")
    assert info is not None
    assert info.version == "1.5.0"
    assert info.url == _GH_RELEASE["html_url"]
    assert info.download_url == "https://example.com/Quodeq-1.5.0-macOS.dmg"
    assert info.is_security is False
    assert info.etag == '"abc"'


def test_security_flag_from_body() -> None:
    rel = {**_GH_RELEASE, "body": "[security] fixes CVE-1234"}
    with patch("quodeq.update.source.httpx.get", return_value=_resp(payload=rel)):
        info = fetch_latest("frozen")
    assert info is not None and info.is_security is True


def test_wheel_takes_version_from_pypi() -> None:
    def fake_get(url, *a, **k):
        if "pypi.org" in url:
            return _resp(payload={"info": {"version": "1.6.0"}})
        return _resp(payload=_GH_RELEASE)

    with patch("quodeq.update.source.httpx.get", side_effect=fake_get):
        info = fetch_latest("wheel")
    assert info is not None and info.version == "1.6.0"
    assert info.url == _GH_RELEASE["html_url"]  # changelog still from GitHub


def test_not_modified_returns_sentinel() -> None:
    with patch("quodeq.update.source.httpx.get", return_value=_resp(status=304, etag='"abc"')):
        info = fetch_latest("frozen", etag='"abc"')
    assert info is not None and info.not_modified is True
    assert info.etag == '"abc"'


def test_network_error_returns_none() -> None:
    with patch("quodeq.update.source.httpx.get", side_effect=httpx.ConnectError("offline")):
        assert fetch_latest("frozen") is None


def test_bad_json_returns_none() -> None:
    r = _resp()
    r.json.side_effect = ValueError("bad json")
    with patch("quodeq.update.source.httpx.get", return_value=r):
        assert fetch_latest("frozen") is None


def test_non_dict_json_returns_none() -> None:
    # Valid JSON that is a list, not an object — must not raise.
    r = _resp()
    r.json.return_value = ["not", "a", "dict"]  # bypass the `payload or {}` default
    with patch("quodeq.update.source.httpx.get", return_value=r):
        assert fetch_latest("frozen") is None
