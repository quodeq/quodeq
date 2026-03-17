"""Fetch and cache OWASP ASVS Level 1 requirements into the standards directory."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from quodeq.shared.utils import write_text, get_asvs_url, show_diff

_logger = logging.getLogger(__name__)

_ASVS_SHA256_ENV = "QUODEQ_ASVS_SHA256"
_ASVS_DEFAULT_LEVEL = 1
_ASVS_ALLOWED_HOSTS = frozenset({"raw.githubusercontent.com", "github.com", "owasp.org"})
_ASVS_OUTPUT_DIR = "asvs"
_ASVS_OUTPUT_FILE = "level1.json"


_DEFAULT_ASVS_VERSION = "4.0.3"


def _asvs_version(override: str | None = None) -> str:
    """Return the ASVS version string. *override* bypasses env for testing."""
    if override is not None:
        return override
    return os.environ.get("QUODEQ_ASVS_VERSION", _DEFAULT_ASVS_VERSION)

_DEFAULT_FETCH_TIMEOUT_S = 30
_RETRY_BASE_DELAY_S = 0.5
_RETRY_JITTER_S = 0.3


def _fetch_with_retry(url: str, timeout: int = _DEFAULT_FETCH_TIMEOUT_S, max_retries: int = 3) -> bytes:
    """Fetch URL content with exponential-backoff retries.

    Retries on network errors up to *max_retries* times, raising
    ``ConnectionError`` if all attempts fail.
    """
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


def _verify_integrity(
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
        _logger.warning(
            "No ASVS hash pinned — accepting first download. "
            "Pin for future integrity checks with %s=%s",
            _ASVS_SHA256_ENV,
            actual_hash,
        )


def _parse_asvs_content(content: bytes) -> list[dict]:
    """Decode JSON content and extract L1 requirements."""
    try:
        raw = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"ASVS response is not valid JSON: {exc}") from exc
    return _parse_asvs_l1(raw)


def fetch_asvs_l1(
    standards_dir: Path,
    *,
    dry_run: bool = False,
    expected_hash: str | None = None,
    skip_integrity: bool | None = None,
) -> int:
    """Fetch OWASP ASVS L1 requirements and write to standards_dir/asvs/level1.json.

    Returns the number of requirements fetched.

    Parameter *expected_hash* defaults to ``None``, in which case the value
    is read from the ``QUODEQ_ASVS_SHA256`` environment variable.
    *skip_integrity* defaults to ``None`` (treated as ``False``); the
    ``QUODEQ_ASVS_SKIP_INTEGRITY`` env var is no longer honored.
    Pass *skip_integrity* explicitly for programmatic use (e.g. tests).
    """
    url = get_asvs_url()
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.hostname not in _ASVS_ALLOWED_HOSTS:
        raise ValueError(
            f"ASVS URL host {parsed.hostname!r} is not in the allowlist. "
            f"Allowed: {', '.join(sorted(_ASVS_ALLOWED_HOSTS))}"
        )
    content = _fetch_with_retry(url)
    _verify_integrity(content, expected_hash, skip_integrity)
    requirements = _parse_asvs_content(content)

    output = {
        "source": f"OWASP ASVS {_asvs_version()}",
        "level": _ASVS_DEFAULT_LEVEL,
        "fetched": date.today().isoformat(),
        "requirements": requirements,
    }

    out_path = standards_dir / _ASVS_OUTPUT_DIR / _ASVS_OUTPUT_FILE
    if dry_run:
        show_diff(out_path, json.dumps(output, indent=2))
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_text(out_path, json.dumps(output, indent=2))

    return len(requirements)


def _parse_asvs_l1(raw: dict) -> list[dict]:
    """Extract all Level-1-required items from the full ASVS JSON structure."""
    requirements = []
    for chapter in raw.get("Requirements", []):
        requirements.extend(_extract_l1_from_chapter(chapter))
    return requirements


def _extract_l1_from_chapter(chapter: dict) -> list[dict]:
    """Extract L1-required items from a single ASVS chapter."""
    items = []
    for section in chapter.get("Items", []):
        for req in section.get("Items", []):
            if req.get("L1", {}).get("Required"):
                shortcode = req.get("Shortcode")
                if not shortcode:
                    continue
                items.append({
                    "id": shortcode,
                    "level": 1,
                    "text": req.get("Description", ""),
                    "cwe": req.get("CWE", []),
                    "section": chapter.get("ShortName", ""),
                })
    return items
