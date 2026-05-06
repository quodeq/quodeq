"""Project-local precedent matching for the context-enricher pipeline.

A precedent is a finding that was previously dismissed for this project.
On the next evaluation, the scanner will likely surface the same code
pattern again; without precedent tracking, the user has to dismiss it
every run. This module computes a stable fingerprint for each dismissed
finding so the post-LLM pipeline can downweight matches.

Fingerprint = sha256 of ``(req, normalized_snippet)``. Whitespace and
trailing punctuation are normalized so cosmetic edits to surrounding
code don't break the match. Code identifiers are *not* normalized:
renaming a variable produces legitimately different code.

The global cross-project precedent corpus (sentence-transformer
embeddings) is a follow-up; this module ships exact-match only.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

_logger = logging.getLogger(__name__)

_DISMISSED_FILENAME = "dismissed.json"
_WS_RE = re.compile(r"\s+")


def _normalize_snippet(snippet: str | None) -> str:
    """Collapse runs of whitespace and trim trailing punctuation/space."""
    if not snippet:
        return ""
    collapsed = _WS_RE.sub(" ", snippet).strip()
    return collapsed.rstrip(",;.")


def fingerprint(req: str | None, snippet: str | None) -> str | None:
    """Hex sha256 of ``req + '|' + normalized_snippet``, or None when blank.

    Returning None for blank inputs lets callers skip lookup entirely
    instead of poisoning the precedent set with a useless all-empty key.
    """
    norm = _normalize_snippet(snippet)
    req_part = (req or "").strip()
    if not req_part and not norm:
        return None
    payload = f"{req_part}|{norm}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_precedent_fingerprints(project_dir: Path) -> set[str]:
    """Load fingerprints for every dismissed finding in *project_dir*.

    Reads ``<project_dir>/dismissed.json``. Missing / malformed files
    return an empty set: precedent matching degrades gracefully and never
    breaks an evaluation.
    """
    if not project_dir or not project_dir.is_dir():
        return set()
    path = project_dir / _DISMISSED_FILENAME
    if not path.exists():
        return set()
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Could not read precedent corpus at %s: %s", path, exc)
        return set()
    if not isinstance(entries, list):
        return set()
    out: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fp = fingerprint(entry.get("req"), entry.get("snippet"))
        if fp is not None:
            out.add(fp)
    return out
