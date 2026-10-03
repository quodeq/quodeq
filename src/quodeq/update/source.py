"""Fetch the latest version from PyPI / GitHub. Fail-silent: returns None on
any error so the caller can never be broken by the network."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable

import httpx

from quodeq import __version__
from quodeq.update.channel import CHANNEL_FROZEN, CHANNEL_WHEEL
from quodeq.update.compare import normalize

_logger = logging.getLogger(__name__)

_PYPI_URL = "https://pypi.org/pypi/quodeq/json"
_GH_LATEST_URL = "https://api.github.com/repos/quodeq/quodeq/releases/latest"
_TIMEOUT = 2.0


@dataclass
class LatestInfo:
    """One release as ``fetch_latest`` saw it, ready to fold into ``UpdateState``.

    ``not_modified`` means the ETag matched and no other field is meaningful.
    """

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


# The dashboard app's own release artifact per platform. Deliberately excludes
# QuodeqBar-*.dmg: first-asset ordering used to hand the menubar DMG (or the
# Windows zip) to the macOS dashboard app's download button.
_ASSET_PATTERNS = {
    "darwin": ("Quodeq-", "-macOS.dmg"),
    "win32": ("Quodeq-", "-Windows.zip"),
}


def _pick_download_url(release: dict, channel: str, platform: str) -> str | None:
    if channel != CHANNEL_FROZEN:
        return None
    pattern = _ASSET_PATTERNS.get(platform)
    if pattern is None:
        return None
    prefix, suffix = pattern
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        url = asset.get("browser_download_url")
        if url and name.startswith(prefix) and name.endswith(suffix):
            return url
    return None


def fetch_latest(
    channel: str, etag: str | None = None, platform: str | None = None,
    *, http_get: Callable[..., httpx.Response] | None = None,
) -> LatestInfo | None:
    """Ask GitHub for the latest release, returning None on any failure.

    Passing the stored *etag* turns an unchanged release into a cheap 304 and a
    ``not_modified`` result. On the wheel channel the version is then corrected
    against PyPI, since a tag can exist before the upload lands; if that lookup
    fails the GitHub tag stands. *platform* defaults to ``sys.platform`` and
    only selects which frozen-app asset becomes ``download_url``. *http_get*
    defaults to ``httpx.get`` (tests pass a fake) and is used for both the
    GitHub and PyPI requests.
    """
    get = http_get if http_get is not None else httpx.get
    headers = {"User-Agent": _user_agent(), "Accept": "application/vnd.github+json"}
    if etag:
        headers["If-None-Match"] = etag
    try:
        gh = get(_GH_LATEST_URL, headers=headers, timeout=_TIMEOUT)
        if gh.status_code == HTTPStatus.NOT_MODIFIED:
            return LatestInfo(not_modified=True, etag=etag)
        if gh.status_code != HTTPStatus.OK:
            return None
        release = gh.json()
        if not isinstance(release, dict):
            return None
        new_etag = gh.headers.get("ETag")
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return None

    version = normalize(str(release.get("tag_name") or "")) or None
    info = LatestInfo(
        version=version,
        url=release.get("html_url"),
        download_url=_pick_download_url(release, channel, platform or sys.platform),
        is_security=_is_security(release),
        etag=new_etag,
    )

    if channel == CHANNEL_WHEEL:
        try:
            pypi = get(_PYPI_URL, headers={"User-Agent": _user_agent()}, timeout=_TIMEOUT)
            if pypi.status_code == HTTPStatus.OK:
                pypi_data = pypi.json()
                if not isinstance(pypi_data, dict):
                    raise ValueError("unexpected non-dict PyPI response")
                pypi_version = normalize(str(pypi_data.get("info", {}).get("version") or ""))
                if pypi_version:
                    info.version = pypi_version
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            _logger.debug("PyPI version lookup failed, keeping the GitHub tag: %s", exc)
    return info
