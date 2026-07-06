"""Read-through cache of rescored per-run dimension scalars.

Keyed by a content-hash version of the project's dismissals/deletions + grade
params, so any change auto-invalidates. Disposable/best-effort: a corrupt or
older-schema db is rebuilt, and any cache error falls through to recompute.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import DimensionResult
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.shared._env import get_score_cache_path, score_cache_disabled

_logger = logging.getLogger(__name__)
_BUSY_TIMEOUT_MS = 5000
# Bumped when the cache *writer* semantics change in a way that could have
# produced bad rows, to invalidate everything written by the prior writer.
# "2": earlier writers persisted in-progress runs' partial scalar sets (e.g. 1
# of 6 dims), which the content-hash version could never invalidate; the
# write-guard now persists only completed runs, and this bump rebuilds the
# stranded partial rows once.
# "3": accumulated / project-summary payloads written before configured-dim
# scoping carried stale dimensions (e.g. clean-architecture) that the project
# no longer evaluates; the run-fingerprint could never invalidate them, so this
# bump rebuilds them once against the latest run's configured-dimension set.
_CACHE_WRITER_EPOCH = "3"
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS run_scalars ("
    " project TEXT NOT NULL, run_id TEXT NOT NULL, version TEXT NOT NULL,"
    " dimension TEXT NOT NULL, overall_score TEXT, overall_grade TEXT,"
    " updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
    " PRIMARY KEY (project, run_id, dimension, version));"
    "CREATE INDEX IF NOT EXISTS idx_run_scalars_lookup ON run_scalars(project, version);"
    "CREATE TABLE IF NOT EXISTS accumulated_cache ("
    " project TEXT NOT NULL, version TEXT NOT NULL, payload TEXT NOT NULL,"
    " updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
    " PRIMARY KEY (project, version));"
    "CREATE TABLE IF NOT EXISTS project_summary_cache ("
    " project TEXT PRIMARY KEY, version TEXT NOT NULL, payload TEXT NOT NULL);"
    "CREATE TABLE IF NOT EXISTS run_keys ("
    " project TEXT NOT NULL, run_id TEXT NOT NULL,"
    " dismiss_keys TEXT NOT NULL, class_keys TEXT NOT NULL,"
    " PRIMARY KEY (project, run_id));"
)


def _init(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        conn.executescript(_SCHEMA)
        conn.commit()
    except sqlite3.DatabaseError:
        # Close before re-raising so the caller's rebuild path can unlink the
        # file with no open handle (Windows raises PermissionError otherwise).
        conn.close()
        raise
    return conn


@contextmanager
def open_score_cache() -> Iterator[sqlite3.Connection]:
    """Open the score cache DB (WAL). Rebuilds from scratch if corrupt/older-schema."""
    path = Path(get_score_cache_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = _init(path)
    except sqlite3.DatabaseError:
        _logger.warning("score cache at %s unreadable; rebuilding", path)
        path.unlink(missing_ok=True)
        conn = _init(path)
    try:
        yield conn
    finally:
        conn.close()


def read_cached_rows(
    conn: sqlite3.Connection, project: str, run_id: str, version: str,
) -> list[DimensionResult] | None:
    """Return cached scalar dims for (project, run_id, version), or None on miss/error."""
    try:
        rows = conn.execute(
            "SELECT dimension, overall_score, overall_grade FROM run_scalars "
            "WHERE project=? AND run_id=? AND version=? ORDER BY dimension",
            (project, run_id, version),
        ).fetchall()
    except sqlite3.Error:
        return None
    if not rows:
        return None
    return [DimensionResult(dimension=r[0], overall_score=r[1], overall_grade=r[2]) for r in rows]


def write_cached_rows(
    conn: sqlite3.Connection, project: str, run_id: str, version: str,
    dims: list[DimensionResult],
) -> None:
    """Replace all cached rows for (project, run_id) with *dims* at *version*.

    Best-effort: logs and returns on any SQLite error (the caller still has the
    computed result).
    """
    try:
        conn.execute("DELETE FROM run_scalars WHERE project=? AND run_id=?", (project, run_id))
        conn.executemany(
            "INSERT OR REPLACE INTO run_scalars "
            "(project, run_id, version, dimension, overall_score, overall_grade) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(project, run_id, version, d.dimension, d.overall_score, d.overall_grade)
             for d in dims if d.dimension],
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("score cache write failed for %s/%s", project, run_id, exc_info=True)


def read_cached_accumulated(
    conn: sqlite3.Connection, project: str, version: str,
) -> dict | None:
    """Return the cached accumulated payload for (project, version), or None."""
    try:
        row = conn.execute(
            "SELECT payload FROM accumulated_cache WHERE project=? AND version=?",
            (project, version),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


def write_cached_accumulated(
    conn: sqlite3.Connection, project: str, version: str, payload: dict,
) -> None:
    """Replace the cached accumulated payload for *project* at *version*.

    Single-slot per project: the DELETE clears any prior version first, so the
    table holds at most one accumulated payload per project. The default
    dashboard uses ``as_of=None`` (one version), so this is stable; rapidly
    alternating distinct ``as_of`` historical views would each miss + overwrite.

    Best-effort: logs and returns on any SQLite/serialization error.
    """
    try:
        blob = json.dumps(payload)
    except (TypeError, ValueError):
        _logger.warning("accumulated payload for %s not serializable; skipping cache", project)
        return
    try:
        conn.execute("DELETE FROM accumulated_cache WHERE project=?", (project,))
        conn.execute(
            "INSERT OR REPLACE INTO accumulated_cache (project, version, payload) VALUES (?, ?, ?)",
            (project, version, blob),
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("accumulated cache write failed for %s", project, exc_info=True)


def _params_fingerprint(params: ScoringParams) -> str:
    """Deterministic serialization of the grade-formula params (sorted maps)."""
    return json.dumps({
        "severity_weight": dict(sorted(params.severity_weight.items())),
        "base_k": params.base_k,
        "lift_compress": params.lift_compress,
        "ceil_scale": params.ceil_scale,
        "floor_minor": params.floor_minor,
        "floor_major": params.floor_major,
        "grade_thresholds": [list(t) for t in params.grade_thresholds],
        "dimension_weights_enabled": params.dimension_weights_enabled,
        "dimension_weights": dict(sorted(params.dimension_weights.items())),
    }, sort_keys=True)


def score_cache_version(project_dir: Path, params: ScoringParams) -> str:
    """Content-hash of the project's dismissals + deletions + grade params.

    Any change to any of these produces a new version, auto-invalidating cached
    rows without a write-path hook.
    """
    payload = json.dumps({
        "epoch": _CACHE_WRITER_EPOCH,
        "dismissed": sorted(str(k) for k in dismissed_keys(project_dir)),
        "deleted": sorted(str(k) for k in deleted_keys(project_dir)),
        "params": _params_fingerprint(params),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_scoped_version(
    params: ScoringParams,
    run_dismiss_keys: set[tuple],
    run_class_keys: set[tuple],
    dismissed_all: set[tuple],
    deleted_all: set[tuple],
) -> str:
    """Version hash for a single run: params + only the suppressions that touch it.

    A run's rescored score depends solely on dismissals whose (req,file,line) is
    in *run_dismiss_keys* and deletions whose (dim,principle,file) is in
    *run_class_keys*, so intersecting keeps unaffected runs' versions stable.
    """
    payload = json.dumps({
        "epoch": _CACHE_WRITER_EPOCH,
        "dismissed": sorted(str(k) for k in (dismissed_all & run_dismiss_keys)),
        "deleted": sorted(str(k) for k in (deleted_all & run_class_keys)),
        "params": _params_fingerprint(params),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def store_run_keys(
    conn: sqlite3.Connection, project: str, run_id: str,
    dismiss_keys: set[tuple], class_keys: set[tuple],
) -> None:
    """Persist a run's key sets (best-effort)."""
    try:
        conn.execute(
            "INSERT OR REPLACE INTO run_keys (project, run_id, dismiss_keys, class_keys) "
            "VALUES (?, ?, ?, ?)",
            (project, run_id,
             json.dumps(sorted(list(k) for k in dismiss_keys)),
             json.dumps(sorted(list(k) for k in class_keys))),
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("run_keys write failed for %s/%s", project, run_id, exc_info=True)


def load_run_keys(
    conn: sqlite3.Connection, project: str,
) -> dict[str, tuple[set[tuple], set[tuple]]]:
    """Return ``{run_id: (dismiss_keys, class_keys)}`` for *project* (empty on error)."""
    out: dict[str, tuple[set[tuple], set[tuple]]] = {}
    try:
        rows = conn.execute(
            "SELECT run_id, dismiss_keys, class_keys FROM run_keys WHERE project=?",
            (project,),
        ).fetchall()
    except sqlite3.Error:
        return {}
    for run_id, dj, cj in rows:
        try:
            out[run_id] = ({tuple(k) for k in json.loads(dj)},
                           {tuple(k) for k in json.loads(cj)})
        except (ValueError, TypeError):
            continue
    return out


def accumulated_cache_version(
    project_dir: Path, params: ScoringParams,
    run_versions: list[tuple[str, str]], as_of: str | None,
) -> str:
    """Version for the accumulated cache: params + the per-run scoped versions +
    *as_of*. Composing per-run versions means a dismiss/delete on one run
    invalidates the accumulated payload only when that run's contribution
    actually changed (its scoped version changed).
    """
    payload = json.dumps({
        # Bump when the accumulated / project-card computation changes, so
        # existing cache entries recompute on deploy instead of serving a stale
        # value until the next scan/dismiss/delete. v3: composed from per-run
        # scoped versions (was base-hash + raw (run_id, status) fingerprint), so
        # a suppression change only invalidates the runs it actually touched.
        "algo": 3,
        "params": _params_fingerprint(params),
        "runs": sorted(list(t) for t in run_versions),
        "as_of": as_of or "",
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def per_run_versions(
    project_dir: Path, project: str, params: ScoringParams, run_ids: list[str],
) -> list[tuple[str, str]]:
    """(run_id, scoped_version) for each run, using persisted/lazy run_keys."""
    from quodeq.services.deleted import deleted_keys  # noqa: PLC0415
    from quodeq.services.dismissed import dismissed_keys  # noqa: PLC0415
    from quodeq.services.run_keys import read_run_key_sets  # noqa: PLC0415
    dismissed, deleted = dismissed_keys(project_dir), deleted_keys(project_dir)
    try:
        with open_score_cache() as conn:
            cached = load_run_keys(conn, project)
    except sqlite3.Error:
        cached = {}
    out: list[tuple[str, str]] = []
    for rid in run_ids:
        keys = cached.get(rid)
        if keys is None:
            keys = read_run_key_sets(project_dir / rid)
            try:
                with open_score_cache() as conn:
                    store_run_keys(conn, project, rid, keys[0], keys[1])
            except sqlite3.Error:
                pass
        out.append((rid, run_scoped_version(params, keys[0], keys[1], dismissed, deleted)))
    return out


def cached_accumulated(
    project: str, version: str, compute: Callable[[], dict],
) -> dict:
    """Read-through cache for the accumulated payload.

    Hit -> return the deserialized cached payload. Miss (or kill switch / cache
    error) -> call *compute*, cache the result best-effort, return it.
    """
    if score_cache_disabled():
        return compute()
    try:
        with open_score_cache() as conn:
            cached = read_cached_accumulated(conn, project, version)
        if cached is not None:
            return cached
    except sqlite3.Error:
        return compute()
    result = compute()
    try:
        with open_score_cache() as conn:
            write_cached_accumulated(conn, project, version, result)
    except sqlite3.Error:
        pass
    return result


def read_cached_project_summary(
    conn: sqlite3.Connection, project: str, version: str,
) -> dict | None:
    """Return the cached project-card summary for (project, version), or None."""
    try:
        row = conn.execute(
            "SELECT payload FROM project_summary_cache WHERE project=? AND version=?",
            (project, version),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


def write_cached_project_summary(
    conn: sqlite3.Connection, project: str, version: str, payload: dict,
) -> None:
    """Single-slot-per-project write for the project-card summary."""
    try:
        blob = json.dumps(payload)
    except (TypeError, ValueError):
        return
    try:
        conn.execute("DELETE FROM project_summary_cache WHERE project=?", (project,))
        conn.execute(
            "INSERT OR REPLACE INTO project_summary_cache (project, version, payload) VALUES (?, ?, ?)",
            (project, version, blob),
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("project summary cache write failed for %s", project, exc_info=True)


def cached_project_summary(
    project: str, version: str, compute: Callable[[], dict],
) -> dict:
    """Read-through cache for the project-card summary (mirrors cached_accumulated)."""
    if score_cache_disabled():
        return compute()
    try:
        with open_score_cache() as conn:
            hit = read_cached_project_summary(conn, project, version)
        if hit is not None:
            return hit
    except sqlite3.Error:
        return compute()
    result = compute()
    try:
        with open_score_cache() as conn:
            write_cached_project_summary(conn, project, version, result)
    except sqlite3.Error:
        pass
    return result


def make_cache_backed_fetcher(
    project: str, version_for: Callable[[str], str],
    base_fetcher: Callable[[str], list[DimensionResult]],
    is_cacheable: Callable[[str], bool] | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Wrap *base_fetcher* with the read-through cache, versioned PER RUN.

    *version_for(run_id)* returns that run's scoped version (params + the
    suppressions touching it). Bulk-loads every cached row for *project* keyed by
    (run_id, version); a hit requires the row's version to equal the run's
    current version, so a dismiss/delete only misses the runs it touches. Misses
    compute via *base_fetcher*, cache scalars at the run's version (only when
    ``is_cacheable``), and return them. Kill switch -> *base_fetcher* unchanged.

    ``is_cacheable`` gates *persistence* per run: only terminal (complete) runs
    are safe. An in-progress run's scalar set grows as dimensions finish, and the
    version hash can't see that, so persisting its partial set would strand a
    stale row -- so opening History mid-scan would leave the trend showing one
    dimension forever while run-detail shows all six. Non-cacheable runs
    compute-through and are served for the current build but never written to
    disk. Defaults to "always cacheable" for backward compatibility.
    """
    if score_cache_disabled():
        return base_fetcher

    by_run_version: dict[tuple[str, str], list[DimensionResult]] = {}
    try:
        with open_score_cache() as conn:
            for rid, ver, dim, score, grade in conn.execute(
                "SELECT run_id, version, dimension, overall_score, overall_grade "
                "FROM run_scalars WHERE project=? ORDER BY run_id, dimension",
                (project,),
            ):
                by_run_version.setdefault((rid, ver), []).append(
                    DimensionResult(dimension=dim, overall_score=score, overall_grade=grade))
    except sqlite3.Error:
        by_run_version = {}

    def fetch(run_id: str) -> list[DimensionResult]:
        version = version_for(run_id)
        hit = by_run_version.get((run_id, version))
        if hit is not None:
            return hit
        dims = base_fetcher(run_id)
        scalars = [DimensionResult(dimension=d.dimension, overall_score=d.overall_score,
                                   overall_grade=d.overall_grade)
                   for d in dims if d.dimension]
        by_run_version[(run_id, version)] = scalars
        if is_cacheable is None or is_cacheable(run_id):
            try:
                with open_score_cache() as conn:
                    write_cached_rows(conn, project, run_id, version, scalars)
            except sqlite3.Error:
                pass
        return scalars

    return fetch
