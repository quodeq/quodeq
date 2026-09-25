"""Retrying file download for self-update.

Isolated from ``selfupdate.py`` so a flaky connection to the release asset
retries on its own, independent of the DMG verification and atomic-swap
logic that follows a successful download.
"""
from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Callable

import httpx

from quodeq.shared.constants import RETRY_BASE_DELAY_S, RETRY_JITTER_S

_TIMEOUT = httpx.Timeout(10.0, read=60.0)
_SERVER_ERROR_STATUS = 500
_DEFAULT_DOWNLOAD_ATTEMPTS = 3  # download_file's retry budget for a flaky release-asset fetch


def download_file(
    url: str,
    dest: Path,
    on_progress: Callable[[int, int], None],
    *,
    attempts: int = _DEFAULT_DOWNLOAD_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Download *url* to *dest*, retrying transient failures.

    Retries on a transport error (connection reset, DNS failure, ...) and on
    a 5xx response; a 4xx (e.g. an expired release asset URL) is not
    retried, since another attempt cannot fix it. Each attempt reopens
    *dest* fresh, discarding any partial write from a prior failed attempt,
    and reports progress via ``on_progress(done, total)``.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=_TIMEOUT) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length") or 0)
                on_progress(0, total)
                done = 0
                with open(dest, "wb") as out:
                    for chunk in response.iter_bytes():
                        out.write(chunk)
                        done += len(chunk)
                        on_progress(done, total)
                return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < _SERVER_ERROR_STATUS:
                raise
            last_exc = exc
        except httpx.TransportError as exc:
            last_exc = exc
        if attempt < attempts - 1:
            sleep(RETRY_BASE_DELAY_S * (2 ** attempt) + random.uniform(0, RETRY_JITTER_S))
    raise last_exc
