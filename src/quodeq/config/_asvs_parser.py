"""Parse ASVS JSON structure and extract Level 1 requirements."""

from __future__ import annotations

import json


def parse_asvs_content(content: bytes) -> list[dict]:
    """Decode JSON content and extract L1 requirements."""
    try:
        raw = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"ASVS response is not valid JSON: {exc}") from exc
    return parse_asvs_l1(raw)


def parse_asvs_l1(raw: dict) -> list[dict]:
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
