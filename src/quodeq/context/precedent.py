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
import logging
import re
from pathlib import Path

_logger = logging.getLogger(__name__)

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

    Aggregates across ``<run_id>/evaluation.db`` under *project_dir*. Missing
    or locked DBs are skipped -- precedent matching degrades gracefully and
    never breaks a scan.

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
        db_path = run_dir / "evaluation.db"
        if not db_path.is_file():
            continue
        try:
            from quodeq.data.sqlite.connection import open_evaluation_db  # noqa: PLC0415
            with open_evaluation_db(run_dir) as conn:
                for row in conn.execute(
                    "SELECT requirement, snippet FROM findings WHERE verdict = 'dismissed'"
                ):
                    fp = fingerprint(row[0], row[1])
                    if fp is not None:
                        out.add(fp)
        except Exception as exc:
            _logger.warning(
                "Could not read precedent corpus from %s: %s", db_path, exc
            )
            continue
    return out
