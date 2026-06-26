"""Fetch the latest version from PyPI / GitHub. Fail-silent: returns None on
any error so the caller can never be broken by the network."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from quodeq import __version__
from quodeq.update.compare import normalize

_PYPI_URL = "https://pypi.org/pypi/quodeq/json"
_GH_LATEST_URL = "https://api.github.com/repos/quodeq/quodeq/releases/latest"
_TIMEOUT = 2.0


@dataclass
class LatestInfo:
    version: str | None = None
    url: str | None = None
    download_url: str | None = None
    is_security: bool = False
    etag: str | None = None
    not_modified: bool = False


def _user_agent() -> str:
    return f"quodeq/{__version__ or 'dev'} update-check"


def _is_security(release: dict) -> bool:
    body = str(release.get("body") or "").lower()
    labels = " ".join(str(label.get("name", "")) for label in release.get("labels") or []).lower()
    return "security" in body or "security" in labels


def _pick_download_url(release: dict) -> str | None:
    assets = release.get("assets") or []
    for asset in assets:
        url = asset.get("browser_download_url")
        if url:
            return url
    return None


def fetch_latest(channel: str, etag: str | None = None) -> LatestInfo | None:
    headers = {"User-Agent": _user_agent(), "Accept": "application/vnd.github+json"}
    if etag:
        headers["If-None-Match"] = etag
    try:
        gh = httpx.get(_GH_LATEST_URL, headers=headers, timeout=_TIMEOUT)
        if gh.status_code == 304:
            return LatestInfo(not_modified=True, etag=etag)
        if gh.status_code != 200:
            return None
        release = gh.json()
        if not isinstance(release, dict):
            return None
        new_etag = gh.headers.get("ETag")
    except (httpx.HTTPError, ValueError):
        return None

    version = normalize(str(release.get("tag_name") or "")) or None
    info = LatestInfo(
        version=version,
        url=release.get("html_url"),
        download_url=_pick_download_url(release),
        is_security=_is_security(release),
        etag=new_etag,
    )

    if channel == "wheel":
        try:
            pypi = httpx.get(_PYPI_URL, headers={"User-Agent": _user_agent()}, timeout=_TIMEOUT)
            if pypi.status_code == 200:
                pypi_data = pypi.json()
                if not isinstance(pypi_data, dict):
                    raise ValueError("unexpected non-dict PyPI response")
                pypi_version = normalize(str(pypi_data.get("info", {}).get("version") or ""))
                if pypi_version:
                    info.version = pypi_version
        except (httpx.HTTPError, ValueError):
            pass  # keep the GitHub tag as the version
    return info
