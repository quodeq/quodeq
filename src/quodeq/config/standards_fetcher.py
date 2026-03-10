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


def fetch_asvs_l1(standards_dir: Path, *, dry_run: bool = False) -> int:
    """Fetch OWASP ASVS L1 requirements and write to standards_dir/asvs/level1.json.

    Returns the number of requirements fetched.
    When QUODEQ_ASVS_SHA256 is set, validates the download against the expected hash.
    """
    with urllib.request.urlopen(get_asvs_url()) as r:
        content = r.read()

    actual_hash = hashlib.sha256(content).hexdigest()
    expected_hash = os.environ.get(_ASVS_SHA256_ENV)
    if expected_hash and actual_hash != expected_hash:
        raise ValueError(
            f"ASVS integrity check failed: expected {expected_hash}, got {actual_hash}"
        )
    if not expected_hash:
        import logging
        logging.getLogger(__name__).warning(
            "ASVS downloaded without integrity verification (set %s=%s to pin)",
            _ASVS_SHA256_ENV,
            actual_hash,
        )

    raw = json.loads(content)

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
                items.append({
                    "id": req["Shortcode"],
                    "level": 1,
                    "text": req["Description"],
                    "cwe": req.get("CWE", []),
                    "section": chapter["ShortName"],
                })
    return items


