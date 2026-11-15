"""The dismissed findings of an archived run, kept beside its archive in ``precedents.json``.

Precedent matching reads every run of a project at every scan. Restoring an
archived run there would un-archive the project's whole history, so the
archive writes what those readers take from ``evaluation.db`` into this
uncompressed sidecar first: the dismissed ``(requirement, snippet)`` pairs,
and the subset eligible as semantic precedents. It is a kept file (never
packed, never restored over); each archive overwrites it.

The SQL lives here so the database readers and the sidecar can never
disagree on what a dismissal is.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from quodeq.core.finding_identity import withheld_snippet
from quodeq.data.fs.run_archive_files import is_plain_file, write_json_sidecar
from quodeq.data.fs.run_archive_wal import DB_NAME

PRECEDENTS_NAME = "precedents.json"
DISMISSED_SQL = "SELECT requirement, snippet FROM findings WHERE verdict = 'dismissed'"
_UNSCOPED = "(scope IS NULL OR scope = '')"
_ON_A_LINE = "line > 0"
SEMANTIC_ELIGIBLE_SQL = (
    "SELECT requirement, snippet FROM findings WHERE verdict = 'dismissed' "
    f"AND {_UNSCOPED} AND {_ON_A_LINE} "
    "AND snippet IS NOT NULL AND TRIM(snippet) <> ''"
)
_NEEDED = frozenset({"verdict", "requirement", "snippet"})
_VERSION = 1
_KINDS = ("dismissed", "semantic")
_PAIR_LEN = 2  # (requirement, snippet)

Pairs = list[tuple[str | None, str | None]]


def write_precedents(run_dir: Path) -> Path | None:
    """Write the sidecar from the run's folded ``evaluation.db``; its path, None without one.

    Reads the main file only (``immutable``): the caller folded the log and
    checks afterwards that nothing wrote meanwhile. An unreadable database
    gets no sidecar, as its dismissals cannot be read while it is live
    either. Raises ``OSError`` when the file cannot be written.
    """
    db, sidecar = run_dir / DB_NAME, run_dir / PRECEDENTS_NAME
    if not db.is_file():
        sidecar.unlink(missing_ok=True)
        return None
    try:
        data = _read(db)
    except sqlite3.DatabaseError:
        sidecar.unlink(missing_ok=True)
        return None
    write_json_sidecar(sidecar, {"version": _VERSION, **data})
    return sidecar


def _read(db: Path) -> dict[str, list[list]]:
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        return {kind: [list(row) for row in conn.execute(sql)] for kind, sql in _queries(conn).items()}
    finally:
        conn.close()


def _queries(conn: sqlite3.Connection) -> dict[str, str]:
    """The sidecar's queries for this database's columns.

    An old run never opened since a migration may lack a column: without a
    verdict (or the pair itself) it cannot hold a dismissal; without
    ``scope`` or ``line`` every dismissal counts as unscoped and on a line.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(findings)")}
    if not _NEEDED <= cols:
        return {kind: "SELECT NULL, NULL WHERE 0" for kind in _KINDS}
    semantic = SEMANTIC_ELIGIBLE_SQL
    for column, clause in (("scope", _UNSCOPED), ("line", _ON_A_LINE)):
        if column not in cols:
            semantic = semantic.replace(clause, "1")
    return {"dismissed": DISMISSED_SQL, "semantic": semantic}


def read_precedents(run_dir: Path, kind: str) -> Pairs:
    """The sidecar's *kind* pairs (``dismissed`` or ``semantic``); empty without a sidecar.

    A sidecar that is not a plain file (a symlink) reads as missing, and a
    row whose values are neither text nor null is skipped. Raises
    ``RuntimeError`` on a malformed sidecar, ``OSError`` on an unreadable one.
    """
    sidecar = run_dir / PRECEDENTS_NAME
    if not is_plain_file(sidecar):
        return []
    try:
        text = sidecar.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        rows = json.loads(text)[kind]
        return [(req, snippet) for req, snippet in rows if _text_or_null(req) and _text_or_null(snippet)]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"malformed {PRECEDENTS_NAME} in {run_dir}: {exc}") from exc


def withhold_precedent_snippets(sidecar: Path) -> None:
    """Rewrite a published copy of the sidecar so it carries no code.

    Each dismissal keeps its requirement and trades its snippet for the token
    holding the snippet's fingerprint, which is all fingerprint matching reads.
    The semantic pairs are dropped: they exist to be embedded as text, and a
    token has none. Anything that is not a well-formed pair is left out rather
    than published as it is.
    """
    try:
        doc = json.loads(sidecar.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        doc = None
    rows = doc.get("dismissed") if isinstance(doc, dict) else None
    pairs = [row for row in rows if _is_pair(row)] if isinstance(rows, list) else []
    dismissed = [[req, None if snippet is None else withheld_snippet(req, snippet)] for req, snippet in pairs]
    write_json_sidecar(sidecar, {"version": _VERSION, "dismissed": dismissed, "semantic": []})


def _is_pair(row: object) -> bool:
    return isinstance(row, list) and len(row) == _PAIR_LEN and all(_text_or_null(value) for value in row)


def _text_or_null(value: object) -> bool:
    return value is None or isinstance(value, str)


def precedents_stamp(run_dir: Path) -> tuple[int, ...] | None:
    """``(size, mtime_ns)`` of the sidecar, None without one (or when it is not a plain file)."""
    sidecar = run_dir / PRECEDENTS_NAME
    if not is_plain_file(sidecar):
        return None
    try:
        st = sidecar.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)
