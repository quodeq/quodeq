"""Fetch and cache OWASP ASVS Level 1 requirements into the standards directory."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from datetime import date
from pathlib import Path

from quodeq.shared.utils import get_asvs_url, show_diff

_ASVS_SHA256_ENV = "QUODEQ_ASVS_SHA256"
_ASVS_SKIP_INTEGRITY_ENV = "QUODEQ_ASVS_SKIP_INTEGRITY"

_RETRY_BASE_DELAY_S = 0.5
_RETRY_JITTER_S = 0.3


def _fetch_with_retry(url: str, timeout: int = 30, max_retries: int = 3) -> bytes:
    """Fetch URL content with exponential-backoff retries.

    Retries on network errors up to *max_retries* times, raising
    ``ConnectionError`` if all attempts fail.
    """
    import random
    import time

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(_RETRY_BASE_DELAY_S * (2 ** attempt) + random.uniform(0, _RETRY_JITTER_S))
    raise ConnectionError(f"Failed to fetch after {max_retries} attempts: {last_exc}") from last_exc


def fetch_asvs_l1(
    standards_dir: Path,
    *,
    dry_run: bool = False,
    expected_hash: str | None = None,
    skip_integrity: bool | None = None,
) -> int:
    """Fetch OWASP ASVS L1 requirements and write to standards_dir/asvs/level1.json.

    Returns the number of requirements fetched.

    Parameters *expected_hash* and *skip_integrity* default to ``None``, in
    which case the values are read from the ``QUODEQ_ASVS_SHA256`` and
    ``QUODEQ_ASVS_SKIP_INTEGRITY`` environment variables respectively.
    Passing them explicitly avoids the need for env-var mutation in tests.
    """
    content = _fetch_with_retry(get_asvs_url())

    actual_hash = hashlib.sha256(content).hexdigest()
    if expected_hash is None:
        expected_hash = os.environ.get(_ASVS_SHA256_ENV)
    if skip_integrity is None:
        skip_integrity = os.environ.get(_ASVS_SKIP_INTEGRITY_ENV) == "1"
    if expected_hash and actual_hash != expected_hash:
        raise ValueError(
            f"ASVS integrity check failed: expected {expected_hash}, got {actual_hash}"
        )
    if not expected_hash:
        if skip_integrity:
            import logging
            logging.getLogger(__name__).warning(
                "ASVS integrity verification skipped (pin with %s=%s)",
                _ASVS_SHA256_ENV,
                actual_hash,
            )
        else:
            raise ValueError(
                f"ASVS integrity verification required: set {_ASVS_SHA256_ENV}={actual_hash} "
                f"to pin this download, or set {_ASVS_SKIP_INTEGRITY_ENV}=1 to bypass"
            )

    try:
        raw = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"ASVS response is not valid JSON: {exc}") from exc

    requirements = _parse_asvs_l1(raw)
    output = {
        "source": "OWASP ASVS 4.0.3",
        "level": 1,
        "fetched": date.today().isoformat(),
        "requirements": requirements,
    }

    out_path = standards_dir / "asvs" / "level1.json"
    if dry_run:
        show_diff(out_path, json.dumps(output, indent=2))
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2))

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


