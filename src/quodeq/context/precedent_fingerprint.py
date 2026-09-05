"""Exact-match precedent fingerprinting.

A precedent is a finding that was previously dismissed for this project.
On the next evaluation, the scanner will likely surface the same code
pattern again; without precedent tracking, the user has to dismiss it
every run. This module computes a stable fingerprint for each dismissed
finding so the post-LLM pipeline can downweight matches.

Fingerprint = sha256 of ``(req, normalized_snippet)``. Whitespace and
trailing punctuation are normalized so cosmetic edits to surrounding
code don't break the match. Code identifiers are *not* normalized:
renaming a variable produces legitimately different code.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from quodeq.data.ports.precedents import DismissedSnippetsReader

_WS_RE = re.compile(r"\s+")
_logger = logging.getLogger(__name__)


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


def precedent_text(req: str | None, snippet: str | None) -> str | None:
    """Canonical text embedded for a finding -- used on BOTH store and match
    sides so the comparison is symmetric. None when both parts are blank.

    Note: ``.rstrip()`` on top of ``_normalize_snippet`` mops up the trailing
    space that punctuation-stripping can leave behind (e.g. "x = 1 ;" ->
    "x = 1 "); it's applied here rather than in ``_normalize_snippet``
    itself so ``fingerprint()``'s hash stays byte-for-byte unchanged.
    """
    norm = _normalize_snippet(snippet).rstrip()
    req_part = (req or "").strip()
    if not req_part and not norm:
        return None
    return f"{req_part}\n\n{norm}"


def load_precedent_fingerprints(
    project_dir: Path, *, read_dismissed: DismissedSnippetsReader,
) -> set[str]:
    """Load fingerprints for every dismissed finding in *project_dir*.

    Aggregates across ``<run_id>/evaluation.db`` under *project_dir*. Missing
    or locked DBs are skipped -- precedent matching degrades gracefully and
    never breaks a scan.

    *read_dismissed* is the injected Protocol seam (see
    ``data/ports/precedents.py``); this module never imports the concrete
    SQLite adapter itself. Composition roots wire the production default --
    ``quodeq.data.sqlite.findings_queries.read_dismissed_snippets`` -- at
    their own call sites (``analysis/_api_runner.py::_build_router_context``,
    ``analysis/mcp/findings_server.py::_build_router``); tests inject a fake
    reader directly.

    Legacy note: prior to PR 1 (live-grades), dismissals were stored in
    ``<project_dir>/dismissed.json``. The migration in
    ``data/migrations/dismissed_json_to_actions_log.py`` folds those legacy
    entries into ``actions.jsonl`` on first projection, so once a project has
    been opened post-deploy the SQL rows also capture the historical data.
    """
    if not project_dir or not project_dir.is_dir():
        return set()

    out: set[str] = set()
    for run_dir in project_dir.iterdir():
        if not run_dir.is_dir():
            continue
        try:
            entries = list(read_dismissed(run_dir))
        except Exception as exc:  # noqa: BLE001 - missing/locked DBs must not fail a scan
            _logger.warning("Skipping precedent read for %s: %s", run_dir, exc)
            continue
        for req, snippet in entries:
            fp = fingerprint(req, snippet)
            if fp is not None:
                out.add(fp)
    return out
