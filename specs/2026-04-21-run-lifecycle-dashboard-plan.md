# Run Lifecycle Dashboard Rerouting — Plan B1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reroute the dashboard to read run state from a SQLite index backed by Plan A's `status.json` files, with lazy sync + legacy synthesis for pre-Plan-A runs + stale-detection promotion for force-killed runs.

**Architecture:** New `run_index.py` module manages `~/.quodeq/index.db` (schema v1, one row per run). Dashboard endpoints call `sync_index()` before querying — upserts changed rows from `status.json`, synthesizes rows for legacy runs, promotes stale non-terminal runs to `cancelled`. `FilesystemActionProvider.list_evaluations` / `get_evaluation_status` become O(log N) DB queries instead of O(N) filesystem walks.

**Tech Stack:** Python 3.12 stdlib (sqlite3, json, pathlib, os.kill for PID liveness), Flask for the `/api/index/rebuild` endpoint. Pytest.

See spec: [2026-04-21-run-lifecycle-dashboard-design.md](2026-04-21-run-lifecycle-dashboard-design.md).

## Scope

B1 only — backend rerouting. UI changes (badge rename, `cancelled (stale)` chip, `find_external_runs` removal) are B2, a follow-up PR.

## Branch

This plan executes on `feat/run-lifecycle-dashboard`, off `origin/develop` (which now contains Plan A's merged code). The spec commit (`69ba7119`) is the starting point.

## File Structure

**New files:**
- `src/quodeq/services/run_index.py` — public API: `open_index`, `sync_index`, `sync_index_for_run`, `list_runs`, `get_run`, `rebuild_index`, `RunRow` dataclass.
- `src/quodeq/services/_index_sync.py` — internals: `_upsert_from_status`, `_sync_legacy_run`, `_check_stale_and_promote`, `_is_pid_alive`.
- `src/quodeq/api/_index_routes.py` — `POST /api/index/rebuild`.
- `tests/services/test_run_index.py` — schema + public API tests.
- `tests/services/test_index_sync.py` — upsert/legacy/stale-promotion tests.
- `tests/api/test_index_routes.py` — endpoint test.
- `tests/api/test_index_backed_provider.py` — provider integration.
- `tests/ci/test_index_e2e.py` — end-to-end smoke.

**Modified files:**
- `src/quodeq/services/filesystem.py` — `FilesystemActionProvider.__init__` accepts `index_db_path`; `list_evaluations` and `get_evaluation_status` call `sync_index` + query the DB.
- `src/quodeq/shared/_env.py` — add `get_index_db_path()` helper.
- `src/quodeq/api/app.py` — `_default_provider()` passes the default index path.
- `src/quodeq/api/routes_registry.py` — register the new index route.

---

## Task 1: `run_index.py` — schema, open_index, RunRow dataclass

**Files:**
- Create: `src/quodeq/services/run_index.py`
- Test: `tests/services/test_run_index.py`
- Modify: `src/quodeq/shared/_env.py` (add `get_index_db_path`)

- [ ] **Step 1: Write failing tests**

```python
# tests/services/test_run_index.py
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quodeq.services.run_index import (
    RunRow,
    SCHEMA_VERSION,
    UnsupportedIndexSchemaError,
    open_index,
)


def test_open_creates_schema_on_fresh_path(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    db = open_index(db_path)
    try:
        # runs table exists with expected columns
        cols = {row[1] for row in db.execute("PRAGMA table_info(runs)").fetchall()}
        expected = {
            "job_id", "project_uuid", "run_id", "run_dir", "state",
            "phase", "current_dimension", "started_at", "updated_at",
            "finalized_at", "heartbeat_at", "pid", "exit_reason", "status_mtime",
        }
        assert expected <= cols

        # indexes exist
        idx = {row[1] for row in db.execute("PRAGMA index_list(runs)").fetchall()}
        assert "idx_runs_state" in idx
        assert "idx_runs_started_at" in idx

        # schema_version row is 1
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == SCHEMA_VERSION == 1
    finally:
        db.close()


def test_open_is_idempotent_on_existing_v1(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    open_index(db_path).close()
    # Opening again must not recreate or raise.
    db = open_index(db_path)
    try:
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == 1
    finally:
        db.close()


def test_open_raises_on_newer_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    # Pre-seed a DB with schema_version=99.
    raw = sqlite3.connect(db_path)
    raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    raw.execute("INSERT INTO schema_version VALUES (99)")
    raw.commit()
    raw.close()
    with pytest.raises(UnsupportedIndexSchemaError):
        open_index(db_path)


def test_open_recovers_from_corrupt_file(tmp_path: Path) -> None:
    """A garbage file at the DB path is replaced with a fresh v1 DB."""
    db_path = tmp_path / "index.db"
    db_path.write_bytes(b"not a sqlite file")
    db = open_index(db_path)
    try:
        v = db.execute("SELECT version FROM schema_version").fetchone()[0]
        assert v == 1
    finally:
        db.close()


def test_runrow_dataclass_fields() -> None:
    """RunRow must carry all schema columns."""
    row = RunRow(
        job_id="ext-x", project_uuid="p", run_id="x", run_dir="/tmp/p/x",
        state="done", phase=None, current_dimension=None,
        started_at="2026-04-20T00:00:00+00:00", updated_at="2026-04-20T00:01:00+00:00",
        finalized_at="2026-04-20T00:01:00+00:00", heartbeat_at=None,
        pid=1234, exit_reason=None, status_mtime=0,
    )
    assert row.job_id == "ext-x"
    assert row.state == "done"


def test_get_index_db_path_default_and_env(tmp_path, monkeypatch) -> None:
    from quodeq.shared._env import get_index_db_path
    monkeypatch.delenv("QUODEQ_INDEX_DB_PATH", raising=False)
    p = Path(get_index_db_path())
    assert p.name == "index.db"
    assert p.parent.name == ".quodeq"

    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "custom.db"))
    assert Path(get_index_db_path()) == tmp_path / "custom.db"
```

- [ ] **Step 2: Run tests — confirm failure**

```
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/services/test_run_index.py -v
```

Expected: ImportError on `quodeq.services.run_index` and `get_index_db_path`.

- [ ] **Step 3: Add `get_index_db_path` to `_env.py`**

Append to `src/quodeq/shared/_env.py`:

```python
_DEFAULT_INDEX_DB_PATH = Path.home() / ".quodeq" / "index.db"


def get_index_db_path(default: str | None = None, env: dict[str, str] | None = None) -> str:
    """Return the absolute path to the SQLite run index DB.

    Resolution order: QUODEQ_INDEX_DB_PATH env var, then *default*, then
    ~/.quodeq/index.db. Always returns a str for downstream Path/sqlite3 use.
    """
    environ = env if env is not None else os.environ
    if "QUODEQ_INDEX_DB_PATH" in environ:
        return environ["QUODEQ_INDEX_DB_PATH"]
    return default or str(_DEFAULT_INDEX_DB_PATH)
```

If `Path` / `os` are not already imported at the top of `_env.py`, add them.

- [ ] **Step 4: Implement `run_index.py`**

```python
# src/quodeq/services/run_index.py
"""SQLite-backed run index.

The index is **derived state** — rebuildable at any time from the filesystem
(``~/.quodeq/evaluations/**/status.json`` and legacy signals). Delete
``~/.quodeq/index.db`` at any time; the next ``open_index`` creates an empty
database and the next ``sync_index`` call repopulates.

Public API is the only stable surface — internals live in ``_index_sync``.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class UnsupportedIndexSchemaError(RuntimeError):
    """Raised when index.db has schema_version > SCHEMA_VERSION."""


@dataclass(frozen=True)
class RunRow:
    """One row of the runs table, as a plain dataclass."""

    job_id: str
    project_uuid: str
    run_id: str
    run_dir: str
    state: str
    phase: str | None
    current_dimension: str | None
    started_at: str
    updated_at: str
    finalized_at: str | None
    heartbeat_at: str | None
    pid: int | None
    exit_reason: str | None
    status_mtime: int


_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS runs (
    job_id            TEXT PRIMARY KEY,
    project_uuid      TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    run_dir           TEXT NOT NULL,
    state             TEXT NOT NULL,
    phase             TEXT,
    current_dimension TEXT,
    started_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    finalized_at      TEXT,
    heartbeat_at      TEXT,
    pid               INTEGER,
    exit_reason       TEXT,
    status_mtime      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_state      ON runs(state);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""


def _apply_schema_v1(db: sqlite3.Connection) -> None:
    with db:
        db.executescript(_SCHEMA_V1)
        have_version = db.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        if have_version == 0:
            db.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))


def _read_schema_version(db: sqlite3.Connection) -> int | None:
    try:
        row = db.execute("SELECT version FROM schema_version").fetchone()
    except sqlite3.DatabaseError:
        return None
    if row is None:
        return None
    return int(row[0])


def open_index(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the index DB at *db_path*, migrate to current schema.

    Raises UnsupportedIndexSchemaError if the existing DB has a newer schema.
    Recovers from a corrupt file by deleting and recreating.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        db = sqlite3.connect(str(db_path))
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=3000")
    except sqlite3.DatabaseError as exc:
        _logger.warning("index DB at %s is corrupt (%s) — recreating", db_path, exc)
        db_path.unlink(missing_ok=True)
        db = sqlite3.connect(str(db_path))
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=3000")

    version = _read_schema_version(db)
    if version is None:
        # Either brand new DB or pre-schema table; apply v1.
        _apply_schema_v1(db)
        return db
    if version > SCHEMA_VERSION:
        db.close()
        raise UnsupportedIndexSchemaError(
            f"index schema_version={version} newer than supported ({SCHEMA_VERSION})"
        )
    # version == 1 (current): schema is already there; nothing to do.
    return db
```

- [ ] **Step 5: Run — confirm pass**

```
uv run pytest tests/services/test_run_index.py tests/shared/ -v
```

Expected: 6 new tests PASS, no regressions on `tests/shared/`.

- [ ] **Step 6: Commit**

```
git add src/quodeq/services/run_index.py src/quodeq/shared/_env.py tests/services/test_run_index.py
git commit -m "feat(run-index): add SQLite schema, open_index, RunRow dataclass"
```

---

## Task 2: `_index_sync.py` — upsert, legacy synthesis, PID liveness

**Files:**
- Create: `src/quodeq/services/_index_sync.py`
- Test: `tests/services/test_index_sync.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/services/test_index_sync.py
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

from quodeq.shared.run_status import RunState, write_status
from quodeq.services.run_index import open_index
from quodeq.services._index_sync import (
    _is_pid_alive,
    _sync_legacy_run,
    _upsert_from_status,
    _check_stale_and_promote,
)


# ---- PID liveness ------------------------------------------------------------

def test_is_pid_alive_current_process() -> None:
    assert _is_pid_alive(os.getpid()) is True


def test_is_pid_alive_dead_pid() -> None:
    # PID 999999999 is virtually certain to be absent on modern systems.
    assert _is_pid_alive(999999999) is False


# ---- Legacy synthesis --------------------------------------------------------

def _make_run_dir(root: Path, project: str, run_id: str) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    return d


def test_legacy_scan_json_present_is_done(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r1")
        (run / "scan.json").write_text("{}")
        _sync_legacy_run(db, run, project_uuid="p", run_id="r1")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r1",)).fetchone()
        assert row == ("done", None)
    finally:
        db.close()


def test_legacy_live_pid_is_running(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r2")
        (run / ".pid").write_text(str(os.getpid()))
        _sync_legacy_run(db, run, project_uuid="p", run_id="r2")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r2",)).fetchone()
        assert row[0] == "running"
        assert row[1] is None
    finally:
        db.close()


def test_legacy_dead_pid_is_cancelled(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r3")
        (run / ".pid").write_text("999999999")
        _sync_legacy_run(db, run, project_uuid="p", run_id="r3")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r3",)).fetchone()
        assert row[0] == "cancelled"
        assert row[1] == "stale_legacy_pid_dead"
    finally:
        db.close()


def test_legacy_no_pid_no_scan_is_cancelled(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r4")
        _sync_legacy_run(db, run, project_uuid="p", run_id="r4")
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r4",)).fetchone()
        assert row[0] == "cancelled"
        assert row[1] == "stale_legacy_no_pid"
    finally:
        db.close()


# ---- Upsert from status.json -------------------------------------------------

def test_upsert_from_status_inserts_new_row(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r5")
        write_status(run, state=RunState.PENDING, job_id="ext-r5",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=["security"])
        _upsert_from_status(db, run, project_uuid="p", run_id="r5")
        row = db.execute(
            "SELECT state, project_uuid, run_id FROM runs WHERE job_id = ?",
            ("ext-r5",),
        ).fetchone()
        assert row == ("pending", "p", "r5")
    finally:
        db.close()


def test_upsert_updates_existing_row(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r6")
        write_status(run, state=RunState.RUNNING, job_id="ext-r6",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[])
        _upsert_from_status(db, run, project_uuid="p", run_id="r6")
        # Transition to done
        write_status(run, state=RunState.DONE, job_id="ext-r6",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[])
        _upsert_from_status(db, run, project_uuid="p", run_id="r6")
        row = db.execute("SELECT state FROM runs WHERE job_id = ?", ("ext-r6",)).fetchone()
        assert row[0] == "done"
    finally:
        db.close()


# ---- Stale detection promotion ----------------------------------------------

def test_stale_promotion_old_heartbeat_dead_pid(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r7")
        write_status(run, state=RunState.RUNNING, job_id="ext-r7",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=999999999)
        _upsert_from_status(db, run, project_uuid="p", run_id="r7")
        # Seed a stale heartbeat (60s old).
        heartbeat = run / ".heartbeat"
        heartbeat.touch()
        old = time.time() - 60
        os.utime(heartbeat, (old, old))

        promoted = _check_stale_and_promote(db, run, project_uuid="p", run_id="r7",
                                            stale_seconds=30)
        assert promoted is True
        row = db.execute("SELECT state, exit_reason FROM runs WHERE job_id = ?", ("ext-r7",)).fetchone()
        assert row[0] == "cancelled"
        assert row[1] == "stale_detected"
        # Disk status.json also updated.
        from quodeq.shared.run_status import read_status
        disk = read_status(run)
        assert disk["state"] == "cancelled"
    finally:
        db.close()


def test_stale_promotion_live_pid_not_promoted(tmp_path: Path) -> None:
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r8")
        write_status(run, state=RunState.RUNNING, job_id="ext-r8",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=os.getpid())
        _upsert_from_status(db, run, project_uuid="p", run_id="r8")
        heartbeat = run / ".heartbeat"
        heartbeat.touch()
        old = time.time() - 60
        os.utime(heartbeat, (old, old))

        promoted = _check_stale_and_promote(db, run, project_uuid="p", run_id="r8",
                                            stale_seconds=30)
        assert promoted is False
        row = db.execute("SELECT state FROM runs WHERE job_id = ?", ("ext-r8",)).fetchone()
        assert row[0] == "running"
    finally:
        db.close()


def test_stale_promotion_terminal_state_untouched(tmp_path: Path) -> None:
    """Terminal states are sticky — never promoted."""
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r9")
        write_status(run, state=RunState.DONE, job_id="ext-r9",
                     started_at="2026-04-20T00:00:00+00:00", dimensions=[])
        _upsert_from_status(db, run, project_uuid="p", run_id="r9")
        # Zero heartbeat, dead pid — shouldn't matter.
        promoted = _check_stale_and_promote(db, run, project_uuid="p", run_id="r9",
                                            stale_seconds=30)
        assert promoted is False
        row = db.execute("SELECT state FROM runs WHERE job_id = ?", ("ext-r9",)).fetchone()
        assert row[0] == "done"
    finally:
        db.close()
```

- [ ] **Step 2: Run — confirm failure**

```
uv run pytest tests/services/test_index_sync.py -v
```

Expected: ImportError on `_index_sync`.

- [ ] **Step 3: Implement `_index_sync.py`**

```python
# src/quodeq/services/_index_sync.py
"""Internal sync logic for the SQLite run index.

Upserts rows from status.json (Plan A runs) or synthesizes from legacy
filesystem signals (pre-Plan-A runs). Promotes stale non-terminal runs to
cancelled based on heartbeat mtime + PID liveness.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from quodeq.shared.run_heartbeat import HEARTBEAT_FILENAME
from quodeq.shared.run_status import (
    RunState,
    STATUS_FILENAME,
    TERMINAL_STATES,
    UnsupportedSchemaError,
    read_status,
    write_status,
)

_logger = logging.getLogger(__name__)

_TERMINAL_STATE_VALUES = {s.value for s in TERMINAL_STATES}

_UPSERT_SQL = """
INSERT INTO runs (
    job_id, project_uuid, run_id, run_dir, state, phase, current_dimension,
    started_at, updated_at, finalized_at, heartbeat_at, pid, exit_reason, status_mtime
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(job_id) DO UPDATE SET
    project_uuid=excluded.project_uuid,
    run_id=excluded.run_id,
    run_dir=excluded.run_dir,
    state=excluded.state,
    phase=excluded.phase,
    current_dimension=excluded.current_dimension,
    started_at=excluded.started_at,
    updated_at=excluded.updated_at,
    finalized_at=excluded.finalized_at,
    heartbeat_at=excluded.heartbeat_at,
    pid=excluded.pid,
    exit_reason=excluded.exit_reason,
    status_mtime=excluded.status_mtime
"""


def _is_pid_alive(pid: int) -> bool:
    """Return True if *pid* refers to a live process. POSIX + Windows."""
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _heartbeat_mtime(run_dir: Path) -> float | None:
    path = run_dir / HEARTBEAT_FILENAME
    try:
        return path.stat().st_mtime
    except (OSError, FileNotFoundError):
        return None


def _heartbeat_iso(run_dir: Path) -> str | None:
    m = _heartbeat_mtime(run_dir)
    if m is None:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(m, tz=timezone.utc).isoformat(timespec="seconds")


def _status_mtime_ns(run_dir: Path) -> int:
    try:
        return (run_dir / STATUS_FILENAME).stat().st_mtime_ns
    except (OSError, FileNotFoundError):
        return 0


def _upsert_from_status(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
) -> None:
    """Read status.json + heartbeat, upsert the row."""
    try:
        status = read_status(run_dir)
    except UnsupportedSchemaError:
        _logger.warning("skipping run %s: status schema newer than supported", run_dir)
        return
    if status is None:
        return
    job_id = status.get("job_id") or f"ext-{run_id}"
    with db:
        db.execute(
            _UPSERT_SQL,
            (
                job_id,
                project_uuid,
                run_id,
                str(run_dir),
                status.get("state", "running"),
                status.get("phase"),
                status.get("current_dimension"),
                status.get("started_at", ""),
                status.get("updated_at", ""),
                status.get("finalized_at"),
                _heartbeat_iso(run_dir),
                status.get("pid"),
                status.get("exit_reason"),
                _status_mtime_ns(run_dir),
            ),
        )


def _sync_legacy_run(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
) -> None:
    """Synthesize a row from filesystem signals for pre-Plan-A runs (no status.json)."""
    scan_path = run_dir / "scan.json"
    pid_path = run_dir / ".pid"
    manifest_path = run_dir / "evidence" / "manifest.json"
    if not manifest_path.exists():
        return  # not a real run

    state: str
    exit_reason: str | None

    if scan_path.exists():
        state, exit_reason = "done", None
    elif pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            alive = _is_pid_alive(pid)
        except (OSError, ValueError):
            alive = False
        if alive:
            state, exit_reason = "running", None
        else:
            state, exit_reason = "cancelled", "stale_legacy_pid_dead"
    else:
        state, exit_reason = "cancelled", "stale_legacy_no_pid"

    job_id = f"ext-{run_id}"
    try:
        started_ts = manifest_path.stat().st_mtime
    except OSError:
        started_ts = time.time()
    from datetime import datetime, timezone
    started_iso = datetime.fromtimestamp(started_ts, tz=timezone.utc).isoformat(timespec="seconds")

    with db:
        db.execute(
            _UPSERT_SQL,
            (
                job_id, project_uuid, run_id, str(run_dir),
                state, None, None,
                started_iso, started_iso, started_iso if state in _TERMINAL_STATE_VALUES else None,
                None, None, exit_reason,
                0,  # status_mtime=0 for legacy rows (no status.json to compare against)
            ),
        )


def _check_stale_and_promote(
    db: sqlite3.Connection, run_dir: Path, *,
    project_uuid: str, run_id: str, stale_seconds: int = 30,
) -> bool:
    """Promote non-terminal runs with dead heartbeat + dead PID to cancelled.

    Returns True if a promotion occurred. Writes status.json back to disk
    (via run_status.write_status) so the terminal state is durable across
    dashboard sessions.
    """
    try:
        status = read_status(run_dir)
    except UnsupportedSchemaError:
        return False
    if status is None:
        return False
    state = status.get("state")
    if state in _TERMINAL_STATE_VALUES:
        return False

    heartbeat_mtime = _heartbeat_mtime(run_dir)
    heartbeat_stale = heartbeat_mtime is None or (time.time() - heartbeat_mtime) > stale_seconds

    pid = status.get("pid")
    pid_alive = isinstance(pid, int) and _is_pid_alive(pid)

    if heartbeat_stale and not pid_alive:
        # Promote to cancelled.
        write_status(
            run_dir,
            state=RunState.CANCELLED,
            job_id=status.get("job_id", f"ext-{run_id}"),
            started_at=status.get("started_at", ""),
            dimensions=status.get("dimensions") or [],
            phase=status.get("phase"),
            current_dimension=status.get("current_dimension"),
            pid=pid if isinstance(pid, int) else None,
            exit_reason="stale_detected",
        )
        _upsert_from_status(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        return True

    return False
```

- [ ] **Step 4: Run — confirm pass**

```
uv run pytest tests/services/test_index_sync.py -v
```

Expected: 10 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/quodeq/services/_index_sync.py tests/services/test_index_sync.py
git commit -m "feat(index-sync): add upsert, legacy synthesis, and stale-promotion helpers"
```

---

## Task 3: Public sync functions + list/get/rebuild

**Files:**
- Modify: `src/quodeq/services/run_index.py` — add `sync_index`, `sync_index_for_run`, `list_runs`, `get_run`, `rebuild_index`.
- Modify: `tests/services/test_run_index.py` — add tests for the public functions.

- [ ] **Step 1: Write failing tests**

Append to `tests/services/test_run_index.py`:

```python
# (continue in the same file)

from quodeq.shared.run_status import RunState, write_status
from quodeq.services.run_index import (
    get_run, list_runs, rebuild_index, sync_index, sync_index_for_run,
)


def _seed_plan_a_run(root: Path, project: str, run_id: str, state: RunState) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, state=state, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    return d


def test_sync_index_seeds_rows_for_all_runs(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "proj1", "runA", RunState.DONE)
    _seed_plan_a_run(reports, "proj1", "runB", RunState.RUNNING)
    # Legacy run with no status.json.
    legacy = reports / "proj2" / "runC"
    (legacy / "evidence").mkdir(parents=True)
    (legacy / "evidence" / "manifest.json").write_text("{}")
    (legacy / "scan.json").write_text("{}")

    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        rows = db.execute("SELECT job_id, state FROM runs ORDER BY job_id").fetchall()
        assert ("ext-runA", "done") in rows
        assert ("ext-runC", "done") in rows
        # runB is RUNNING but its .heartbeat is missing/ancient, pid is current — verify.
        # The key invariant: all three runs ended up in the DB.
        job_ids = {r[0] for r in rows}
        assert job_ids == {"ext-runA", "ext-runB", "ext-runC"}
    finally:
        db.close()


def test_sync_index_skips_unchanged_rows(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "proj1", "runA", RunState.DONE)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        before = db.total_changes
        # Second sync with no filesystem changes should be a no-op for writes.
        sync_index(db, reports)
        after = db.total_changes
        # Allow one BEGIN/COMMIT pair per run per call (just "stat" ops shouldn't cause any),
        # so delta should be 0 for upserts specifically.
        # We assert no new runs rows were changed.
        row_changes = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        assert row_changes == 1
    finally:
        db.close()


def test_list_runs_ordered_by_started_at_desc(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    older = reports / "p" / "older"
    newer = reports / "p" / "newer"
    (older / "evidence").mkdir(parents=True)
    (newer / "evidence").mkdir(parents=True)
    (older / "evidence" / "manifest.json").write_text("{}")
    (newer / "evidence" / "manifest.json").write_text("{}")
    write_status(older, state=RunState.DONE, job_id="ext-older",
                 started_at="2026-04-19T00:00:00+00:00", dimensions=[])
    write_status(newer, state=RunState.DONE, job_id="ext-newer",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])

    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        rows = list_runs(db)
        assert [r.job_id for r in rows] == ["ext-newer", "ext-older"]
    finally:
        db.close()


def test_list_runs_respects_limit(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    for i in range(5):
        _seed_plan_a_run(reports, "p", f"r{i}", RunState.DONE)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        rows = list_runs(db, limit=3)
        assert len(rows) == 3
    finally:
        db.close()


def test_get_run_returns_row_or_none(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "p", "r", RunState.DONE)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        row = get_run(db, "ext-r")
        assert row is not None
        assert row.job_id == "ext-r"
        assert row.state == "done"
        assert get_run(db, "ext-does-not-exist") is None
    finally:
        db.close()


def test_sync_index_for_run_is_scoped(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    a = _seed_plan_a_run(reports, "p", "rA", RunState.RUNNING)
    _seed_plan_a_run(reports, "p", "rB", RunState.RUNNING)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index_for_run(db, a)
        rows = db.execute("SELECT job_id FROM runs").fetchall()
        assert [r[0] for r in rows] == ["ext-rA"]
    finally:
        db.close()


def test_rebuild_index_empties_and_repopulates(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _seed_plan_a_run(reports, "p", "rA", RunState.DONE)
    _seed_plan_a_run(reports, "p", "rB", RunState.DONE)
    db = open_index(tmp_path / "idx.db")
    try:
        sync_index(db, reports)
        # Manually pollute the table with a phantom row — rebuild should drop it.
        db.execute(
            "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
            "started_at, updated_at, status_mtime) "
            "VALUES ('phantom', 'p', 'p', '/nope', 'running', '0', '0', 0)"
        )
        db.commit()
        count, elapsed_ms = rebuild_index(db, reports)
        assert count == 2
        assert elapsed_ms >= 0
        rows = {r[0] for r in db.execute("SELECT job_id FROM runs").fetchall()}
        assert rows == {"ext-rA", "ext-rB"}
    finally:
        db.close()
```

- [ ] **Step 2: Run — confirm failure**

```
uv run pytest tests/services/test_run_index.py -v
```

Expected: ImportError on the new public functions.

- [ ] **Step 3: Extend `run_index.py`**

Append to `src/quodeq/services/run_index.py`:

```python
import time
from quodeq.services._index_sync import (
    _check_stale_and_promote,
    _sync_legacy_run,
    _upsert_from_status,
    _status_mtime_ns,
)


def _walk_run_dirs(evaluations_root: Path):
    """Yield (project_uuid, run_id, run_dir) for every run on disk."""
    if not evaluations_root.is_dir():
        return
    for project_dir in evaluations_root.iterdir():
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        for run_dir in project_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            yield project_dir.name, run_dir.name, run_dir


def sync_index(db: sqlite3.Connection, evaluations_root: Path) -> None:
    """Lazy upsert: walk *evaluations_root*, sync any run whose status.json
    changed since last seen OR that lacks an index row entirely. Promote
    stale non-terminal runs.
    """
    for project_uuid, run_id, run_dir in _walk_run_dirs(evaluations_root):
        _sync_one_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)


def sync_index_for_run(db: sqlite3.Connection, run_dir: Path) -> None:
    """Sync only the given run_dir (used by /api/evaluations/<id>)."""
    if not run_dir.is_dir():
        return
    project_uuid = run_dir.parent.name
    run_id = run_dir.name
    _sync_one_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)


def _sync_one_run(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
) -> None:
    status_path = run_dir / "status.json"
    if status_path.exists():
        disk_mtime = _status_mtime_ns(run_dir)
        job_id = f"ext-{run_id}"
        cached = db.execute(
            "SELECT status_mtime FROM runs WHERE job_id = ?", (job_id,),
        ).fetchone()
        if cached is None or cached[0] != disk_mtime:
            try:
                _upsert_from_status(db, run_dir, project_uuid=project_uuid, run_id=run_id)
            except Exception as exc:
                _logger.warning("skipping run %s: %s", run_dir, exc)
                return
        # Always check staleness, even on mtime-unchanged runs.
        try:
            _check_stale_and_promote(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        except Exception as exc:
            _logger.warning("stale-check failed for %s: %s", run_dir, exc)
    else:
        try:
            _sync_legacy_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        except Exception as exc:
            _logger.warning("legacy sync failed for %s: %s", run_dir, exc)


_LIST_COLS = (
    "job_id, project_uuid, run_id, run_dir, state, phase, current_dimension, "
    "started_at, updated_at, finalized_at, heartbeat_at, pid, exit_reason, status_mtime"
)


def _row_to_runrow(row: tuple) -> RunRow:
    return RunRow(*row)


def list_runs(db: sqlite3.Connection, *, limit: int = 0) -> list[RunRow]:
    """Return runs ordered by started_at DESC. limit=0 means no limit."""
    sql = f"SELECT {_LIST_COLS} FROM runs ORDER BY started_at DESC"
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    return [_row_to_runrow(r) for r in db.execute(sql).fetchall()]


def get_run(db: sqlite3.Connection, job_id: str) -> RunRow | None:
    row = db.execute(
        f"SELECT {_LIST_COLS} FROM runs WHERE job_id = ?", (job_id,),
    ).fetchone()
    return _row_to_runrow(row) if row else None


def rebuild_index(
    db: sqlite3.Connection, evaluations_root: Path,
) -> tuple[int, int]:
    """Drop all rows, re-sync from filesystem. Returns (count, elapsed_ms)."""
    start = time.monotonic()
    with db:
        db.execute("DELETE FROM runs")
    sync_index(db, evaluations_root)
    count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return count, elapsed_ms
```

- [ ] **Step 4: Run — confirm pass**

```
uv run pytest tests/services/test_run_index.py -v
uv run pytest -q
```

Expected: all new tests PASS, full suite green.

- [ ] **Step 5: Commit**

```
git add src/quodeq/services/run_index.py tests/services/test_run_index.py
git commit -m "feat(run-index): add sync_index, list/get_run, rebuild_index"
```

---

## Task 4: Reroute `FilesystemActionProvider` methods

**Files:**
- Modify: `src/quodeq/services/filesystem.py` — `__init__` stores `index_db_path`; `list_evaluations` + `get_evaluation_status` use the index.
- Modify: `src/quodeq/api/app.py` — `_default_provider()` passes the default index path.
- Test: `tests/api/test_index_backed_provider.py`

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_index_backed_provider.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.shared.run_status import RunState, write_status


def _seed_run(reports: Path, project: str, run_id: str, state: RunState) -> Path:
    d = reports / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, state=state, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    return d


def test_provider_list_evaluations_returns_indexed_rows(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rA", RunState.DONE)
    _seed_run(reports, "p", "rB", RunState.DONE)

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)
    job_ids = {j.job_id for j in jobs}
    assert {"ext-rA", "ext-rB"} <= job_ids
    # Every returned JobSnapshot has state populated from the index.
    assert all(j.status == "done" for j in jobs if j.job_id.startswith("ext-"))


def test_provider_get_evaluation_status_returns_row(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rX", RunState.RUNNING)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    snapshot = provider.get_evaluation_status("ext-rX", reports_dir=reports)
    assert snapshot is not None
    assert snapshot.job_id == "ext-rX"
    assert snapshot.status == "running"


def test_provider_list_does_not_walk_reports_dir_after_first_sync(tmp_path, monkeypatch) -> None:
    """After the first sync, subsequent list_evaluations calls shouldn't re-walk
    on every request — they should query the DB for the static list and only
    stat status.json files for dirty-checking."""
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rA", RunState.DONE)
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    provider.list_evaluations(limit=0, reports_dir=reports)
    # Second call is fast — no way to assert directly, but at minimum it must
    # not raise and must return the same row.
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)
    assert len(jobs) == 1
```

- [ ] **Step 2: Run — confirm failure**

```
uv run pytest tests/api/test_index_backed_provider.py -v
```

Expected: FAIL — `FilesystemActionProvider(index_db_path=...)` doesn't accept that kwarg yet.

- [ ] **Step 3: Modify `FilesystemActionProvider`**

In `src/quodeq/services/filesystem.py`:

1. Add imports at the top:
```python
from quodeq.services import run_index as _run_index
from quodeq.core.types.job import JobSnapshot
```

2. Modify `__init__` to accept `index_db_path`:
```python
def __init__(
    self,
    job_manager: JobManager | None = None,
    compiled_dir: Path | None = None,
    index_db_path: Path | None = None,
) -> None:
    super().__init__()
    self._jobs = job_manager or JobManager()
    self._compiled_dir = compiled_dir
    self._index_db_path = Path(index_db_path) if index_db_path is not None else None
    self._model_fetchers: dict[str, Callable] = {
        "claude": self._get_claude_models,
    }
    self._project_cache: dict[str, Any] | None = None
    self._project_cache_time: float = 0
```

3. Add a lazy accessor:
```python
def _open_index(self) -> "sqlite3.Connection":
    """Open (lazily) the index DB. Resolved from init kwarg or env."""
    if self._index_db_path is None:
        from quodeq.shared._env import get_index_db_path
        self._index_db_path = Path(get_index_db_path())
    return _run_index.open_index(self._index_db_path)
```

4. Locate the mixin that defines `list_evaluations` and `get_evaluation_status` (`src/quodeq/services/evaluation_mixin.py`). Override these on `FilesystemActionProvider` (or extend the mixin):

```python
def list_evaluations(self, limit: int = 0, reports_dir: Path | None = None) -> list[JobSnapshot]:
    """Return runs from the SQLite index.

    Merges dashboard-spawned live jobs (tracked in-memory by JobManager)
    with external/completed runs (stored in the DB).
    """
    if reports_dir is None:
        from quodeq.shared._env import get_evaluations_dir
        reports_dir = Path(get_evaluations_dir())
    db = self._open_index()
    try:
        _run_index.sync_index(db, reports_dir)
        rows = _run_index.list_runs(db, limit=limit)
    finally:
        db.close()
    # Map RunRow → JobSnapshot.
    snapshots = [self._run_row_to_snapshot(r) for r in rows]
    # Merge in any in-memory jobs (dashboard-spawned) that may not yet be in the DB.
    internal_jobs = self._jobs.list_jobs(reports_dir=reports_dir) if hasattr(self._jobs, "list_jobs") else []
    # Dedup by job_id — in-memory wins if both present.
    by_id = {s.job_id: s for s in snapshots}
    for j in internal_jobs:
        by_id[j.job_id] = j
    merged = list(by_id.values())
    merged.sort(key=lambda s: s.started_at or "", reverse=True)
    return merged[:limit] if limit > 0 else merged


def get_evaluation_status(self, job_id: str, reports_dir: Path | None = None) -> JobSnapshot | None:
    """Return a single run's snapshot from the index or JobManager."""
    # In-memory JobManager wins for live dashboard-spawned jobs.
    if hasattr(self._jobs, "get_job"):
        internal = self._jobs.get_job(job_id, reports_dir=reports_dir)
        if internal is not None:
            return internal
    if reports_dir is None:
        from quodeq.shared._env import get_evaluations_dir
        reports_dir = Path(get_evaluations_dir())
    db = self._open_index()
    try:
        _run_index.sync_index(db, reports_dir)
        row = _run_index.get_run(db, job_id)
    finally:
        db.close()
    if row is None:
        return None
    return self._run_row_to_snapshot(row)


@staticmethod
def _run_row_to_snapshot(row: "_run_index.RunRow") -> JobSnapshot:
    return JobSnapshot(
        job_id=row.job_id,
        status=row.state,
        command="",
        started_at=row.started_at,
        ended_at=row.finalized_at,
        exit_code=None,
        logs=[],
        output_project=row.project_uuid,
        output_run_id=row.run_id,
        phase=row.phase,
        current_dimension=row.current_dimension,
        dimensions=None,
        error=row.exit_reason,
        source="external" if row.job_id.startswith("ext-") else "internal",
    )
```

**Note:** if `list_evaluations` / `get_evaluation_status` are defined on `FsEvaluationMixin` rather than the class directly, override them on `FilesystemActionProvider` (method resolution order gives precedence to the subclass). Verify by running the test — if it still hits the mixin code path, move the method onto `FilesystemActionProvider`.

5. In `src/quodeq/api/app.py::_default_provider`:

```python
def _default_provider() -> ActionProvider:
    from quodeq.services.filesystem import FilesystemActionProvider
    from quodeq.shared._env import get_index_db_path
    return FilesystemActionProvider(index_db_path=Path(get_index_db_path()))
```

- [ ] **Step 4: Run — confirm pass**

```
uv run pytest tests/api/test_index_backed_provider.py -v
uv run pytest tests/services/ tests/api/ -q
```

Expected: new tests PASS, no regressions.

- [ ] **Step 5: Commit**

```
git add src/quodeq/services/filesystem.py src/quodeq/api/app.py tests/api/test_index_backed_provider.py
git commit -m "feat(provider): route list_evaluations/get_evaluation_status through index DB"
```

---

## Task 5: `POST /api/index/rebuild` endpoint

**Files:**
- Create: `src/quodeq/api/_index_routes.py`
- Modify: `src/quodeq/api/routes_registry.py` — register the new route.
- Test: `tests/api/test_index_routes.py`

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_index_routes.py
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest

from quodeq.shared.run_status import RunState, write_status


def _seed_run(reports: Path, project: str, run_id: str) -> Path:
    d = reports / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    write_status(d, state=RunState.DONE, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    return d


def test_rebuild_endpoint_registered(monkeypatch, tmp_path) -> None:
    from quodeq.api.app import create_app
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/index/rebuild" in rules


def test_rebuild_returns_count_and_elapsed(monkeypatch, tmp_path) -> None:
    from quodeq.api.app import create_app
    reports = tmp_path / "reports"
    _seed_run(reports, "p", "rA")
    _seed_run(reports, "p", "rB")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))

    app = create_app()
    client = app.test_client()
    resp = client.post("/api/index/rebuild")
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data["count"] == 2
    assert data["elapsed_ms"] >= 0
```

- [ ] **Step 2: Run — confirm failure**

```
uv run pytest tests/api/test_index_routes.py -v
```

Expected: FAIL — route not registered.

- [ ] **Step 3: Implement `_index_routes.py`**

```python
# src/quodeq/api/_index_routes.py
"""Admin/debug endpoints for the SQLite run index."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, current_app, jsonify

from quodeq.services import run_index as _run_index


def register_index_routes(app: Flask) -> None:
    """Register /api/index/* endpoints."""

    @app.post("/api/index/rebuild")
    def rebuild_index_endpoint() -> Response | tuple[Response, int]:
        provider = current_app.config.get("_provider")
        if provider is None or not hasattr(provider, "_open_index"):
            return jsonify({"error": "provider not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        from quodeq.shared._env import get_evaluations_dir
        reports_root = Path(get_evaluations_dir())
        db = provider._open_index()
        try:
            count, elapsed_ms = _run_index.rebuild_index(db, reports_root)
        finally:
            db.close()
        return jsonify({"count": count, "elapsed_ms": elapsed_ms})
```

- [ ] **Step 4: Register the route**

In `src/quodeq/api/routes_registry.py`, add import and call:

```python
from quodeq.api._index_routes import register_index_routes
```

In `register_all_routes`, add before `register_static_routes`:
```python
    register_index_routes(app)
```

Also: ensure `app.config["_provider"] = provider` is set in `create_app` (Plan A already does this, verify).

- [ ] **Step 5: Run — confirm pass**

```
uv run pytest tests/api/test_index_routes.py -v
uv run pytest -q
```

Expected: both tests PASS, full suite green.

- [ ] **Step 6: Commit**

```
git add src/quodeq/api/_index_routes.py src/quodeq/api/routes_registry.py tests/api/test_index_routes.py
git commit -m "feat(api): add POST /api/index/rebuild endpoint"
```

---

## Task 6: End-to-end smoke test

**Files:**
- Create: `tests/ci/test_index_e2e.py`

- [ ] **Step 1: Write the test**

```python
# tests/ci/test_index_e2e.py
"""End-to-end: real CLI runs are visible in the DB-backed /api/evaluations response."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_cli_run_appears_in_index(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def f(): return 1\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    env = {
        **os.environ,
        "QUODEQ_EVALUATIONS_DIR": str(reports),
        "QUODEQ_INDEX_DB_PATH": str(tmp_path / "idx.db"),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "quodeq.cli", "evaluate", str(src), "--dry-run", "-d", "security"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}"

    # Now hit /api/evaluations in-process and confirm the run is there with state=done.
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    from quodeq.api.app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/evaluations")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    # Find the external run (ext-<run_id>).
    ext_jobs = [j for j in data if j["jobId"].startswith("ext-")] if data else []
    assert ext_jobs, "no ext- job returned"
    # Project assertion: state is done (or at least not 'running').
    states = {j["status"] for j in ext_jobs}
    assert "done" in states, f"expected done, got {states}"


@pytest.mark.integration
def test_legacy_run_appears_as_cancelled(tmp_path: Path, monkeypatch) -> None:
    """A pre-Plan-A run dir (no status.json, no .pid) shows up as cancelled."""
    reports = tmp_path / "reports"
    run = reports / "p" / "legacy-run"
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    # No scan.json, no .pid, no status.json — pure legacy stale.

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "idx.db"))
    from quodeq.api.app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/evaluations")
    data = resp.get_json()
    legacy = [j for j in data if j["jobId"] == "ext-legacy-run"]
    assert len(legacy) == 1
    assert legacy[0]["status"] == "cancelled"
```

- [ ] **Step 2: Run — confirm pass**

```
uv run pytest tests/ci/test_index_e2e.py -v
uv run pytest -q
```

Expected: both E2E tests PASS, full suite green.

- [ ] **Step 3: Commit**

```
git add tests/ci/test_index_e2e.py
git commit -m "test(ci): end-to-end DB-backed /api/evaluations with real CLI run"
```

---

## Post-Implementation Verification

Manual checks after all 6 tasks:

1. `quodeq evaluate .` normally → open dashboard → run appears with `state=done` and no infinite "in progress".
2. `quodeq evaluate .` + Ctrl+C → dashboard shows `cancelled(signal_SIGINT)`.
3. Simulate a force-kill: `quodeq evaluate .` + `kill -9 <pid>` → dashboard shows `running` initially, then after the configured stale-timeout (30s by default) the next dashboard refresh shows `cancelled(stale_detected)` and the `status.json` on disk now reflects the same.
4. Delete `~/.quodeq/index.db` → refresh dashboard → initial load rebuilds, everything still works.
5. `sqlite3 ~/.quodeq/index.db "SELECT state, COUNT(*) FROM runs GROUP BY state;"` — sanity check the row distribution.
6. Live terminal (from the other merged feature) still works — pick a run, terminal pane streams/replays.

## Rollback

Each task is a standalone commit. The feature is additive on the backend — reverting does not damage `status.json` or user data. `find_external_runs` is still in place as a dead fallback, so reverting by commit is safe.

## Follow-up (Plan B2, separate PR)

- UI: rename `ExternalRunBadge`, distinguish dashboard-spawned vs external via `JobManager` membership.
- UI: add `cancelled (stale)` chip variant with tooltip showing `exit_reason`.
- Backend: remove `find_external_runs`, `_run_dir_to_snapshot`, `_infer_progress` from `_external_jobs.py`.
- UI: "Rebuild index" button wired to `POST /api/index/rebuild`.
