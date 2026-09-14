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
import sqlite3
import threading
from pathlib import Path

from quodeq.data.ports.precedents import DismissedSnippetsReader, DismissedSourceStamp
from quodeq.shared.lru import LRUDict

_WS_RE = re.compile(r"\s+")
_logger = logging.getLogger(__name__)

# Per-run memo: run_dir -> (source stamp, fingerprints read under that stamp).
# Every scan used to open and query every run's DB again; keying the read on
# a cheap stamp makes a settled history cost one stat per run, not one query.
# Bounded LRU so a long-lived server never grows without limit across projects.
PrecedentMemo = LRUDict[Path, tuple[object, frozenset[str]]]
_MEMO_MAX_RUNS = 4096
_memo: PrecedentMemo = LRUDict(_MEMO_MAX_RUNS)
_memo_lock = threading.Lock()


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


def _memo_get(cache: PrecedentMemo, run_dir: Path, stamp: object) -> frozenset[str] | None:
    """Fingerprints memoized for *run_dir* under exactly *stamp*, else None."""
    with _memo_lock:
        hit = cache.get(run_dir)
    if hit is None or hit[0] != stamp:
        return None
    return hit[1]


def _memo_put(cache: PrecedentMemo, run_dir: Path, stamp: object, fps: frozenset[str]) -> None:
    with _memo_lock:
        cache.put(run_dir, (stamp, fps))


def _read_run_fingerprints(
    run_dir: Path, read_dismissed: DismissedSnippetsReader,
) -> frozenset[str] | None:
    """Fingerprints of *run_dir*'s dismissals, or None when the read failed.

    None rather than an empty set so a locked DB is retried on the next scan
    instead of being remembered as having no precedents.
    """
    try:
        entries = list(read_dismissed(run_dir))
    except (RuntimeError, sqlite3.Error, OSError) as exc:
        # RuntimeError: open_evaluation_db wraps locked/missing-file/disk-I/O
        # failures for a clearer path-scoped message (see connection.py).
        # sqlite3.Error: corruption/schema-mismatch (sqlite3.DatabaseError),
        # deliberately left unwrapped there. OSError: run_dir.mkdir() failing
        # before a connection is even attempted.
        _logger.warning("Skipping precedent read for %s: %s", run_dir, exc)
        return None
    fps = (fingerprint(req, snippet) for req, snippet in entries)
    return frozenset(fp for fp in fps if fp is not None)


def load_precedent_fingerprints(
    project_dir: Path,
    *,
    read_dismissed: DismissedSnippetsReader,
    source_stamp: DismissedSourceStamp,
    cache: PrecedentMemo | None = None,
) -> set[str]:
    """Load fingerprints for every dismissed finding in *project_dir*.

    Aggregates across ``<run_id>/evaluation.db`` under *project_dir*. Missing
    or locked DBs are skipped -- precedent matching degrades gracefully and
    never breaks a scan.

    Each run is read at most once per *source_stamp* value (None means the
    run has no source and is skipped outright); the fingerprints read under
    a stamp live in a bounded module-level memo, so a settled history costs
    one stat per run on later scans instead of one DB open and query. Failed
    reads are not memoized. Tests may pass their own *cache* for isolation.

    *read_dismissed* and *source_stamp* are the injected seams (see
    ``data/ports/precedents.py``); this module never imports the concrete
    SQLite adapter. Composition roots wire the production defaults from
    ``quodeq.data.sqlite.findings_queries`` (``read_dismissed_snippets_strict``,
    ``dismissed_source_stamp``) at ``analysis/_api_runner.py::
    _build_router_context`` and ``analysis/mcp/findings_server.py::
    _build_router``. Legacy ``<project_dir>/dismissed.json`` entries reach
    the SQL rows via ``data/migrations/dismissed_json_to_actions_log.py``.
    """
    if not project_dir or not project_dir.is_dir():
        return set()

    memo = _memo if cache is None else cache
    out: set[str] = set()
    for run_dir in project_dir.iterdir():
        if not run_dir.is_dir():
            continue
        stamp = source_stamp(run_dir)
        if stamp is None:
            continue
        fps = _memo_get(memo, run_dir, stamp)
        if fps is None:
            fps = _read_run_fingerprints(run_dir, read_dismissed)
            if fps is None:
                continue
            _memo_put(memo, run_dir, stamp, fps)
        out |= fps
    return out
