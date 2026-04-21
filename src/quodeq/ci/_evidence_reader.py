"""Read violations directly from ``<dim>_evidence.jsonl`` files.

Used by ``quodeq ci report --from-evidence`` in PR diff mode, where no
scored ``evaluation/<dim>.json`` reports exist. Returns the same dict shape
that ``build_review_payload`` consumes from the scored reports, so the
downstream payload builder is unchanged.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

_logger = logging.getLogger(__name__)


def _judgment_to_violation(obj: dict) -> dict | None:
    """Normalize a raw JSONL judgment dict into the payload-builder shape.

    Returns None for non-violation verdicts or malformed rows.
    """
    if obj.get("t") != "violation":
        return None
    file = obj.get("file")
    if not file:
        return None
    out: dict = {
        "file": file,
        "severity": obj.get("severity", "minor"),
        "title": obj.get("w", ""),
        "reason": obj.get("reason", ""),
        "snippet": obj.get("snippet", ""),
        "dimension": obj.get("d", ""),
    }
    line = obj.get("line")
    if line is not None:
        out["line"] = int(line)
    req = obj.get("req")
    if req:
        out["req"] = req
    return out


def load_violations_from_evidence(evidence_dir: Path) -> list[dict]:
    """Scan ``<evidence_dir>/*_evidence.jsonl`` and return normalized violations.

    Malformed lines and non-violation rows are skipped silently (logged at
    DEBUG). Missing directories return an empty list.
    """
    if not evidence_dir.is_dir():
        return []
    violations: list[dict] = []
    for path in sorted(evidence_dir.glob("*_evidence.jsonl")):
        try:
            raw = path.read_text()
        except OSError as exc:
            _logger.debug("Could not read %s: %s", path, exc)
            continue
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                _logger.debug("Skipping malformed line in %s: %s", path, exc)
                continue
            v = _judgment_to_violation(obj)
            if v is not None:
                violations.append(v)
    return violations
