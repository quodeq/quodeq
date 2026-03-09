"""Fetch and cache OWASP ASVS Level 1 requirements into the standards directory."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from pathlib import Path

_DEFAULT_ASVS_URL = (
    "https://raw.githubusercontent.com/OWASP/ASVS/v4.0.3/4.0/docs_en/"
    "OWASP%20Application%20Security%20Verification%20Standard%204.0.3-en.json"
)


def _get_asvs_url() -> str:
    return os.environ.get("QUODEQ_ASVS_URL", _DEFAULT_ASVS_URL)


def fetch_asvs_l1(standards_dir: Path, *, dry_run: bool = False) -> int:
    """Fetch OWASP ASVS L1 requirements and write to standards_dir/asvs/level1.json.

    Returns the number of requirements fetched.
    """
    with urllib.request.urlopen(_get_asvs_url()) as r:
        raw = json.loads(r.read())

    requirements = _parse_asvs_l1(raw)
    output = {
        "source": "OWASP ASVS 4.0.3",
        "level": 1,
        "fetched": date.today().isoformat(),
        "requirements": requirements,
    }

    out_path = standards_dir / "asvs" / "level1.json"
    if dry_run:
        _show_diff(out_path, json.dumps(output, indent=2))
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


def _show_diff(path: Path, new_content: str) -> None:
    import difflib
    old_lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=str(path), tofile="<new>")
    text = "".join(diff)
    if text:
        print(text)
    else:
        print(f"[no changes] {path}")
