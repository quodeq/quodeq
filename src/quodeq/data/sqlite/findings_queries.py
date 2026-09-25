"""Read-only queries over a run's ``findings`` table.

The services layer (dismissed/deleted/run_keys) used to inline this SQL,
which coupled business flows to the schema and pulled sqlite3 into the
service layer. All three reads live here so the schema stays an
adapter-layer detail. Every function is best-effort: an absent or
unreadable database yields empty results, matching the callers'
long-standing behavior.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from quodeq.core.finding_identity import DismissKey, finding_dismiss_keys
from quodeq.data.sqlite._db_stamp_memo import memoized_by_db_stamp
from quodeq.data.sqlite.connection import EVALUATION_DB_FILENAME, open_evaluation_db

_logger = logging.getLogger(__name__)


_SELECT_ACTIVE = (
    "SELECT id, practice_id, dimension, requirement, verdict, severity, "
    "file, line, end_line, title, reason, snippet, violation_type, violation_type_raw, context, "
    "scope, req_refs_json, confidence, provenance_downgrade, "
    "scope_downgrade_json "
    "FROM findings WHERE verdict != 'dismissed' ORDER BY id"
)


def _dict_row(cursor, row):  # noqa: ANN001
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def read_active_findings(run_dir: Path, *, limit: int | None = None) -> Iterator[dict]:
    """Every non-dismissed finding row in *run_dir*, as column-keyed dicts, in id order.

    Feeds the SQL-backed scores response (services.scoring). Rows keep the
    raw column names/values; mapping to ``Finding`` is the caller's concern
    (``row_to_finding``). Rows stream off the cursor while the connection is
    held open, so the only copy in memory is whatever the caller keeps; the
    connection closes once the generator is exhausted or dropped. *limit*
    caps the rows read (SQL ``LIMIT``); the scores builder passes none, it
    needs every row for the per-dimension totals. Unlike the best-effort
    readers in this module, this opens the database unconditionally
    (creating an empty one when absent): callers only reach it after the
    grade tables answered, so the database already exists on every
    production path.
    """
    sql, params = _SELECT_ACTIVE, ()
    if limit is not None:
        sql, params = f"{_SELECT_ACTIVE} LIMIT ?", (limit,)
    with open_evaluation_db(run_dir) as conn:
        conn.row_factory = _dict_row
        yield from conn.execute(sql, params)


# SQLite's compiled-in bind-parameter limit (SQLITE_MAX_VARIABLE_NUMBER)
# defaults to ~999; one param per file keeps each chunk well under that
# regardless of build.
_DETAIL_CHUNK_SIZE = 300

_DETAIL_COLUMNS = (
    "requirement, file, line, dimension, practice_id, severity, "
    "title, reason, snippet, context, scope, end_line, req_refs_json"
)
# Candidate rows are fetched per file (idx_findings_file) and matched in
# Python through finding_dismiss_keys: a dismiss key is either (req, file,
# line) or (req, file, snippet fingerprint), and a finding with no requirement
# id may be keyed on "" or on its practice id, so the SQL side only narrows
# to the files in question.
_DETAIL_SELECT_BY_FILE = f"SELECT {_DETAIL_COLUMNS} FROM findings WHERE file IN ({{values}})"


def _detail_row_to_dict(row: tuple) -> dict:
    req_refs_raw = row[12]
    try:
        req_refs = json.loads(req_refs_raw) if req_refs_raw else []
    except (json.JSONDecodeError, TypeError):
        req_refs = []
    return {
        "req": row[0] or "", "file": row[1] or "", "line": row[2] or 0,
        "dimension": row[3] or "", "principle": row[4] or "",
        "severity": row[5] or "", "title": row[6] or "", "reason": row[7] or "",
        "snippet": row[8] or "", "context": row[9] or "", "scope": row[10] or "",
        "endLine": row[11] or 0, "reqRefs": req_refs,
    }


def _row_dismiss_keys(row: tuple) -> set[DismissKey]:
    """Every dismiss key that would hide the finding in a detail row."""
    return finding_dismiss_keys(
        req=row[0], principle=row[4], file=row[1], line=row[2], snippet=row[8])


def _fetch_detail_rows(
    conn: sqlite3.Connection, wanted: set[DismissKey], out: dict[DismissKey, dict],
) -> None:
    files = sorted({str(k[1] or "") for k in wanted})
    for start in range(0, len(files), _DETAIL_CHUNK_SIZE):
        chunk = files[start:start + _DETAIL_CHUNK_SIZE]
        sql = _DETAIL_SELECT_BY_FILE.format(values=", ".join(["?"] * len(chunk)))
        for row in conn.execute(sql, chunk):
            for key in _row_dismiss_keys(row) & wanted:
                out.setdefault(key, _detail_row_to_dict(row))


def read_finding_details(run_dir: Path, keys: set[DismissKey]) -> dict[DismissKey, dict]:
    """Return finding-detail dicts for the dismiss *keys* present in
    *run_dir*'s findings table.

    A key is ``(req, file, line)`` or ``(req, file, snippet fingerprint)``
    (see ``core.finding_identity``); a finding matches on any identity a
    dismissal of it may have been recorded under. Keys not present are simply
    absent from the result. The SQL ``verdict`` column is ignored on
    purpose: actions.jsonl is the source of truth for *which* findings are
    dismissed; the row only supplies *what* the finding was. A corrupt
    database returns whatever was read before the error.

    Candidate rows are narrowed per file in SQL (``idx_findings_file``) and
    matched in Python; the file list is chunked to stay under SQLite's
    per-statement bind-parameter limit.
    """
    db_path = run_dir / EVALUATION_DB_FILENAME
    if not db_path.is_file() or not keys:
        return {}
    out: dict[DismissKey, dict] = {}
    try:
        with open_evaluation_db(run_dir) as conn:
            _fetch_detail_rows(conn, set(keys), out)
    except (sqlite3.DatabaseError, RuntimeError):
        return out
    return out


def read_run_key_sets(run_dir: Path) -> tuple[set[tuple], set[tuple]]:
    """Return ``(dismiss_keys, class_keys)`` present in *run_dir*'s findings.

    ``dismiss_keys``: every key a dismissal of one of the run's findings may
    be recorded under -- ``(req, file, line)`` and, for findings with a
    snippet, ``(req, file, fingerprint)``, for each accepted identity of the
    finding (``finding_dismiss_keys``). ``class_keys``:
    ``{(dimension, practice_id, file)}``. Keys come from ALL findings
    regardless of verdict, so a dismiss (which only flips a verdict) never
    changes a run's key set.

    Memoized in-process against the database's on-disk stamp
    (``_db_stamp_memo``): the project list and every scores call re-read the
    key sets of each run the score cache does not hold, and hashing every
    snippet again per request cost more than the rest of the request. Callers
    get fresh copies, so the memo can never be mutated through a result.
    """
    keys = memoized_by_db_stamp(
        run_dir / EVALUATION_DB_FILENAME, lambda: _read_run_key_sets_from_db(run_dir))
    if keys is None:
        return set(), set()
    return set(keys[0]), set(keys[1])


def _read_run_key_sets_from_db(run_dir: Path) -> tuple[set[tuple], set[tuple]] | None:
    """Uncached read behind :func:`read_run_key_sets`; None when the db is unreadable."""
    dismiss: set[tuple] = set()
    cls: set[tuple] = set()
    try:
        with open_evaluation_db(run_dir) as conn:
            for req, file, line, dim, pid, snippet in conn.execute(
                "SELECT requirement, file, line, dimension, practice_id, snippet FROM findings"
            ):
                dismiss |= finding_dismiss_keys(
                    req=req, principle=pid, file=file, line=line, snippet=snippet)
                cls.add((str(dim or ""), str(pid or ""), str(file or "")))
    except (sqlite3.DatabaseError, RuntimeError):
        return None
    return dismiss, cls


_SEMANTIC_ELIGIBLE_SQL = (
    "SELECT requirement, snippet FROM findings WHERE verdict = 'dismissed' "
    "AND (scope IS NULL OR scope = '') "
    "AND line > 0 "
    "AND snippet IS NOT NULL AND TRIM(snippet) <> ''"
)


def read_dismissed_snippets_strict(run_dir: Path) -> list[tuple[str | None, str | None]]:
    """``(requirement, snippet)`` for every dismissed finding in *run_dir*.

    Feeds precedent fingerprinting. A missing database means no dismissals
    and yields ``[]``; a database that cannot be opened or read raises
    (``RuntimeError`` from ``open_evaluation_db``, ``sqlite3.Error``,
    ``OSError``). The per-run memo in ``context.precedent_fingerprint``
    depends on seeing the failure: an empty list in its place would be
    remembered as "no dismissals" until the DB's stat happens to change.
    """
    if not (run_dir / EVALUATION_DB_FILENAME).is_file():
        return []
    with open_evaluation_db(run_dir) as conn:
        return [
            (row[0], row[1])
            for row in conn.execute(
                "SELECT requirement, snippet FROM findings WHERE verdict = 'dismissed'"
            )
        ]


def read_dismissed_snippets(run_dir: Path) -> list[tuple[str | None, str | None]]:
    """Best-effort ``read_dismissed_snippets_strict``: any read failure yields
    an empty list, for callers that have no retry of their own and must never
    let precedent matching break a scan."""
    try:
        return read_dismissed_snippets_strict(run_dir)
    except Exception as exc:  # noqa: BLE001 — precedent must never break a scan
        _logger.warning("Could not read dismissed snippets from %s: %s", run_dir, exc)
        return []


def dismissed_source_stamp(run_dir: Path) -> tuple[int, ...] | None:
    """Freshness stamp of *run_dir*'s dismissed findings, or None without a DB.

    ``(size, mtime_ns)`` of ``evaluation.db`` followed by the same for its
    ``-wal`` file when present: connections run in WAL mode, so a dismissal
    committed while another process still holds the database open sits in
    the WAL and leaves the main file's stat untouched until the next
    checkpoint. Keys the per-run memo in ``context.precedent_fingerprint``;
    two stats are far cheaper than the open-plus-query they let it skip.

    The WAL is stat'ed first. A checkpoint moves bytes from the WAL into the
    main file (and on close removes the WAL), so one landing between the two
    stats is caught by the main-file stat that follows. The other order reads
    the old main file, then finds no WAL, and reports the exact stamp taken
    before the dismissal: a stale memo hit.
    """
    db_path = run_dir / EVALUATION_DB_FILENAME
    wal_parts: tuple[int, ...] = ()
    try:
        wal = db_path.with_name(db_path.name + "-wal").stat()
        wal_parts = (wal.st_size, wal.st_mtime_ns)
    except OSError as exc:
        _logger.debug("dismissed-source stamp unreadable: %s", exc)
    try:
        st = db_path.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns, *wal_parts)


def read_semantic_eligible_dismissals(run_dir: Path) -> list[tuple[str | None, str | None]]:
    """``(requirement, snippet)`` for dismissals eligible as semantic precedents.

    Excludes scope-level dismissals and empty-snippet/line<=0 rows, mirroring
    ``_semantic_eligible`` in ``analysis/mcp/enricher.py`` on the match side:
    without the filter a single empty-snippet dismissal would cosine-match
    every future finding under that requirement.
    """
    if not (run_dir / EVALUATION_DB_FILENAME).is_file():
        return []
    try:
        with open_evaluation_db(run_dir) as conn:
            return [(req, snippet) for req, snippet in conn.execute(_SEMANTIC_ELIGIBLE_SQL)]
    except Exception as exc:  # noqa: BLE001 — precedent must never break a scan
        _logger.warning("Could not read dismissed texts from %s: %s", run_dir, exc)
        return []


def find_dismissed_matching(
    run_dir: Path, *, dimension: str, practice_id: str, file: str,
) -> list[tuple[str, str, int, str, str]]:
    """Return ``(requirement, file, line, practice_id, snippet)`` for every
    DISMISSED finding in *run_dir* matching the ``(dimension, practice_id,
    file)`` deletion key. The caller derives the dismiss identities from the
    row (``finding_dismiss_keys``) to find the entries to undismiss."""
    db_path = run_dir / EVALUATION_DB_FILENAME
    if not db_path.is_file():
        return []
    try:
        with open_evaluation_db(run_dir) as conn:
            return [
                (row[0] or "", row[1] or "", int(row[2] or 0), row[3] or "", row[4] or "")
                for row in conn.execute(
                    "SELECT requirement, file, line, practice_id, snippet FROM findings "
                    "WHERE verdict = 'dismissed' AND dimension = ? "
                    "AND practice_id = ? AND file = ?",
                    (dimension, practice_id, file),
                )
            ]
    except (sqlite3.Error, OSError, RuntimeError):
        _logger.warning(
            "Skipping unreadable evaluation.db in %s", run_dir, exc_info=True,
        )
        return []
