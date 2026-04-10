"""Network fetch, retry, and integrity verification for ASVS downloads."""

from __future__ import annotations

import hashlib
import logging
import random
import time
import urllib.error
import urllib.request
import os

_logger = logging.getLogger(__name__)

_ASVS_SHA256_ENV = "QUODEQ_ASVS_SHA256"

_DEFAULT_FETCH_TIMEOUT_S = 30
_RETRY_BASE_DELAY_S = 0.5
_RETRY_JITTER_S = 0.3


def fetch_with_retry(url: str, timeout: int = _DEFAULT_FETCH_TIMEOUT_S, max_retries: int = 3) -> bytes:
    """Fetch URL content with exponential-backoff retries.

    Retries on network errors up to *max_retries* times, raising
    ``ConnectionError`` if all attempts fail.
    """
    if not url.startswith("https://"):
        raise ValueError(f"Only https:// URLs are allowed, got: {url!r}")
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        _logger.info("Fetching %s (attempt %d/%d)", url, attempt + 1, max_retries)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(_RETRY_BASE_DELAY_S * (2 ** attempt) + random.uniform(0, _RETRY_JITTER_S))
    raise ConnectionError(f"Failed to fetch after {max_retries} attempts: {last_exc}") from last_exc


def verify_integrity(
    content: bytes,
    expected_hash: str | None = None,
    skip_integrity: bool | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Verify SHA-256 integrity of downloaded ASVS content.

    Reads defaults from environment variables when *expected_hash* or
    *skip_integrity* are ``None``.

    Raises ``ValueError`` on mismatch or when verification is required but
    no hash is configured.
    """
    actual_hash = hashlib.sha256(content).hexdigest()
    if expected_hash is None:
        expected_hash = (env or os.environ).get("QUODEQ_ASVS_SHA256")
    if skip_integrity is None:
        skip_integrity = False
    if expected_hash and actual_hash != expected_hash:
        raise ValueError(
            f"ASVS integrity check failed: expected {expected_hash}, got {actual_hash}"
        )
    if not expected_hash:
        if skip_integrity:
            _logger.warning(
                "SECURITY: Integrity check skipped — downloaded content is NOT verified. "
                "Pin the hash for production use: %s=%s",
                _ASVS_SHA256_ENV,
                actual_hash,
            )
        else:
            raise ValueError(
                f"No ASVS hash configured — refusing unverified download. "
                f"Set {_ASVS_SHA256_ENV}={actual_hash} to pin the expected hash, "
                f"or pass skip_integrity=True to bypass."
            )
