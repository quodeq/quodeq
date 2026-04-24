# Run Lifecycle — Dashboard Rerouting (Plan B1) Design Spec

**Status:** Draft
**Date:** 2026-04-21
**Author:** Victor + Claude (brainstorm)
**Builds on:** [2026-04-20-run-lifecycle-status-design.md](2026-04-20-run-lifecycle-status-design.md)

## Problem

Plan A (merged as PR #254) made every new CLI evaluation write an authoritative `status.json` with explicit lifecycle transitions, plus a `.heartbeat` file for liveness. But the **dashboard doesn't read `status.json` yet** — it still calls `find_external_runs` which infers state from `manifest.json` present + `scan.json` absent. Result:

- Nightly runs finishing in the new way write `state=done` in `status.json`, but the dashboard continues to show them as "in progress" because `scan.json` is written at a different path (or not at all for some flows).
- Pre-Plan-A runs on disk have no `status.json`, and the old detection has no way to distinguish "genuinely running" from "stale/crashed" — the promotion to `cancelled` requires the stale-detection logic Plan A added to `run_lifecycle.py`, but the dashboard never calls it.
- Listing the dashboard's evaluations re-walks the full `reports_dir` on every poll (O(N) per request). With hundreds of historical runs, this is slow.

Plan B is the dashboard-side counterpart to Plan A.

## Scope

This spec covers **Plan B1** (backend). Plan B2 (UI follow-up) is out of scope here and documented in [Out of Scope](#out-of-scope).

### Plan B1 (this PR)

1. **SQLite index** at `~/.quodeq/index.db` — one row per run, rebuildable from filesystem at any time.
2. **Lazy sync** driven by dashboard read endpoints (`GET /api/evaluations`, `GET /api/evaluations/<id>`). First-ever sync on a fresh install is a full scan; subsequent calls upsert only dirty runs.
3. **Legacy run synthesis** — pre-Plan-A runs (no `status.json`) get synthesized DB rows from filesystem signals (matrix in [2026-04-20-run-lifecycle-status-design.md § Backward Compatibility](2026-04-20-run-lifecycle-status-design.md)). No files are written back to disk.
4. **Stale-detection promotion** — non-terminal runs with dead heartbeat + dead PID are promoted to `cancelled(stale_detected)`. This DOES write `status.json` to disk (via `run_status.write_status`) so the promotion is durable.
5. **`FilesystemActionProvider` rerouting** — `list_evaluations`, `get_evaluation_status`, `get_log_run_dir`, `is_job_complete` read from the DB. `find_external_runs` is left in place but no longer called by provider methods.
6. **`POST /api/index/rebuild`** endpoint for debugging / recovery.

### Plan B2 (follow-up PR, deferred)

- `ExternalRunBadge` rename + re-scope (distinguish dashboard-spawned vs external via `JobManager` membership, not filesystem scan).
- New `cancelled (stale)` chip variant in the UI.
- Deprecate and delete `find_external_runs` once nothing calls it.
- Dashboard list view gets a "rebuild index" button wired to `POST /api/index/rebuild`.

## Goals

1. Dashboard queries are fast — `/api/evaluations` is O(log N) indexed DB query plus incremental `stat` calls, not O(N) filesystem walk.
2. The user's immediate pain (stuck "Evaluation in Progress") is eliminated end-to-end: new runs show correct terminal state, legacy/crashed runs are promoted to `cancelled`.
3. Derived state is disposable — `rm ~/.quodeq/index.db` is a valid recovery step, and `POST /api/index/rebuild` is a live alternative.
4. UI response shape is unchanged — B1 is invisible plumbing. B2 is where users see differences.
5. No regressions on the live-terminal feature (which depends on `get_log_run_dir` still working).

## Non-Goals

- Writing `status.json` back to disk for legacy runs (keeps filesystem as pure audit log; synthesized rows live in DB only).
- Network sync of the index across machines.
- Replacing `JobManager`'s in-memory state — the DB mirrors completed/external runs, `JobManager` stays authoritative for in-flight dashboard-spawned jobs.
- UI changes in B1. All renamings, new chip variants, and badge logic happen in B2.

## Architecture

```
Dashboard request flow (B1)

GET /api/evaluations ─► FilesystemActionProvider.list_evaluations
                         │
                         ├─► open_index(~/.quodeq/index.db)   (creates/migrates if needed)
                         ├─► sync_index(db, reports_root)     (lazy, idempotent)
                         │     │
                         │     ├─► for each run_dir:
                         │     │     ├─► if status.json exists and mtime unchanged → skip
                         │     │     ├─► if status.json exists and mtime changed → upsert
                         │     │     └─► else → _sync_legacy_run() synthesizes row
                         │     │
                         │     └─► for each non-terminal row:
                         │           ├─► if heartbeat > STALE_S old AND pid dead:
                         │           │     ├─► write_status(run_dir, state=cancelled,
                         │           │     │                exit_reason="stale_detected")
                         │           │     └─► re-upsert DB row
                         │           └─► else → leave as-is
                         │
                         └─► list_runs(db, limit) → JobSnapshot[]
```

The DB is derived state with a single authoritative source (`status.json`) and a secondary inference path (legacy filesystem signals for pre-Plan-A runs). `rm ~/.quodeq/index.db` at any time → next `open_index` recreates empty → next `sync_index` repopulates.

## Components

### 1. `src/quodeq/services/run_index.py` (new)

Public API:

```python
from sqlite3 import Connection
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class RunRow:
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
    status_mtime: int  # ns


def open_index(db_path: Path) -> Connection: ...
def sync_index(db: Connection, evaluations_root: Path) -> None: ...
def sync_index_for_run(db: Connection, run_dir: Path) -> None: ...  # single-run scoped sync
def list_runs(db: Connection, *, limit: int = 0) -> list[RunRow]: ...
def get_run(db: Connection, job_id: str) -> RunRow | None: ...
def rebuild_index(db: Connection, evaluations_root: Path) -> tuple[int, int]: ...
  # returns (count, elapsed_ms)
```

### 2. `src/quodeq/services/_index_sync.py` (new)

Internal helpers: `_upsert_from_status`, `_sync_legacy_run`, `_check_stale_and_promote`. Split from `run_index.py` to keep the public module small.

### 3. `src/quodeq/api/_index_routes.py` (new)

```python
@app.post("/api/index/rebuild")
def rebuild_index_endpoint() -> Response:
    provider = current_app.config["_provider"]
    db = provider.open_index()
    reports_root = Path(get_evaluations_dir())
    count, elapsed_ms = run_index.rebuild_index(db, reports_root)
    return jsonify({"count": count, "elapsed_ms": elapsed_ms})
```

Registered in `register_all_routes`. Protected by the global `before_request` hook (no new decorator).

### 4. `src/quodeq/services/filesystem.py` (modify)

`FilesystemActionProvider`:

- `__init__` stores `db_path = Path(get_home_dir()) / ".quodeq" / "index.db"`. Opens lazily on first use.
- `list_evaluations(limit, reports_dir)` calls `sync_index(db, reports_dir)` then `list_runs(db, limit=limit)`, maps rows to `JobSnapshot`.
- `get_evaluation_status(job_id, reports_dir)` calls `sync_index_for_run(db, resolved_run_dir)` then `get_run(db, job_id)`.
- `get_log_run_dir(job_id)` queries the DB; falls back to the existing filesystem walk if the row is missing (defense-in-depth for the transition window).
- `is_job_complete(job_id)` reads `state` from the DB; returns True iff in `{done, failed, cancelled}`.
- `find_external_runs` is **left in place, uncalled**. B2 removes it.

## Data Flow

### First-ever dashboard open on a machine with N existing runs

1. `open_index(~/.quodeq/index.db)` — file doesn't exist → create, apply schema v1, insert `schema_version=1`.
2. `sync_index(db, reports_root)` — walks all N run_dirs, upserts one row each. ~1-5ms per run (one `stat` + one read of `status.json` or legacy synthesis). Total: ~100ms per 100 runs — noticeable, bounded, one-time.
3. `list_runs` returns the full set.
4. Subsequent calls are fast: `sync_index` walks but skips rows whose `status_mtime` hasn't changed. New runs added since last call are the only upserts.

### Fresh CLI run completes while dashboard is open

1. CLI writes `status.json{state:done}` at finalization.
2. Dashboard polls `/api/evaluations`.
3. `sync_index` sees new `status_mtime` for that run → upserts updated row.
4. List returns the run with `state=done`.

### Legacy (pre-Plan-A) run detected

1. `sync_index` finds no `status.json` in run_dir.
2. `_sync_legacy_run` checks filesystem signals:
   - `scan.json` present → synthesize `state=done`.
   - `.pid` present + PID alive → `state=running`.
   - `.pid` present + PID dead → `state=cancelled, exit_reason=stale_legacy_pid_dead`.
   - `.pid` absent → `state=cancelled, exit_reason=stale_legacy_no_pid`.
3. Row written to DB. No filesystem mutation.

### Stale detection on a non-terminal Plan-A run

1. `status.json{state:running}` exists on disk.
2. `.heartbeat` mtime > `QUODEQ_HEARTBEAT_STALE_S` (30s) old.
3. PID from `status.json.pid` is dead (via `os.kill(pid, 0)`).
4. `_check_stale_and_promote` calls `write_status(run_dir, state=cancelled, exit_reason="stale_detected")` — writes new `status.json`.
5. Re-upsert DB row.
6. Next sync reads the updated `status.json` naturally (mtime changed); confirms terminal state.

## Error Handling

See the full table in the "Error Handling" section of [2026-04-20-run-lifecycle-status-design.md](2026-04-20-run-lifecycle-status-design.md). Plan B1 specifically adds:

- **Index file doesn't exist** → `open_index` creates it. First-call latency cost; subsequent calls fast.
- **Index locked under WAL contention** → SQLite backoff, endpoint returns 503 on >3s timeout.
- **Index corrupt** → catch, delete file, recreate empty, rebuild. Endpoint returns normally.
- **Per-run sync error** (bad `status.json`, unreadable run_dir) → catch, log, skip that run, continue. One bad run never breaks the dashboard for others.
- **Stale-promotion write fails** (disk full) → catch, log, DB row stays non-terminal. Next sync retries.

## Configuration

Inherited from the Plan A spec:

| Env var | Default | Purpose |
|---|---|---|
| `QUODEQ_HEARTBEAT_INTERVAL_S` | `5` | (Plan A) CLI heartbeat cadence |
| `QUODEQ_HEARTBEAT_STALE_S` | `30` | Age above which dashboard considers heartbeat stale |

New to B1:

| Env var | Default | Purpose |
|---|---|---|
| `QUODEQ_INDEX_DB_PATH` | `~/.quodeq/index.db` | SQLite index location (useful for tests / multi-profile setups) |
| `QUODEQ_INDEX_LOCK_TIMEOUT_S` | `3` | SQLite busy-timeout before returning 503 on lock contention |

## Testing

### Unit (`tests/services/test_run_index.py`)
- `open_index` creates schema on fresh path; idempotent on existing v1 file.
- `open_index` on v99 DB raises `UnsupportedSchemaError`.
- `rebuild_index` empties and repopulates; return value `(count, elapsed_ms)` sane.

### Unit (`tests/services/test_index_sync.py`)
- Fresh DB + 3 run_dirs (Plan-A done, legacy-done, legacy-stale) → 3 correct rows.
- Unchanged `status_mtime` → `sqlite3.total_changes` delta = 0 for that run.
- Changed `status_mtime` → row upserts with new state.
- `_sync_legacy_run` matrix: 4 filesystem-signal combinations → 4 correct synthesized states.
- Stale-promotion: `status.json{running}` + old `.heartbeat` + dead PID → row becomes `cancelled(stale_detected)`, disk `status.json` updated.
- Concurrent sync from two threads under WAL → no lock errors.

### Integration (`tests/api/test_index_backed_provider.py`)
- `GET /api/evaluations` returns DB-backed rows (verify by comparing to direct DB query, not filesystem walk).
- `GET /api/evaluations/<job_id>` for a fresh Plan-A run matches `status.json` state.
- `GET /api/evaluations/<job_id>` for a legacy stale run returns synthesized `cancelled` row.
- `POST /api/index/rebuild` returns `{count: N, elapsed_ms: M}`, DB repopulated.
- `get_log_run_dir(job_id)` still works (live-terminal SSE regression guard).

### Smoke (`tests/ci/test_index_e2e.py`)
- Real CLI dry-run → dashboard lists the finished run with `state=done`.
- Real CLI killed mid-run (reuse Plan A's Task 5 subprocess pattern) → dashboard lists it as `cancelled`.

## Rollout

1. Land B1 (this PR). Backend is rerouted; UI still shows old `ExternalRunBadge` ("Running outside the dashboard") but now with CORRECT `state` underneath. Stuck "Evaluation in Progress" bug resolves.
2. Monitor for one day. Inspect `~/.quodeq/index.db` manually to confirm rows look right. `sqlite3 ~/.quodeq/index.db "SELECT state, COUNT(*) FROM runs GROUP BY state;"`.
3. Land B2 (UI follow-up): badge rename, stale chip, `find_external_runs` removal.

## Out of Scope

- **B2 UI changes** — documented above; follows this PR.
- **Schema migrations beyond v1** — the migration mechanism is wired, but we ship only v1 here. Future fields (e.g., `cancelled_by_user`, `duration_s`) go in v2.
- **Cross-dashboard-session staleness detection** — only triggered on read; no background thread walking for stale runs. This is fine because any dashboard refresh triggers the check.
- **Protection against malicious `status.json` tampering** — single-user desktop tool.
- **Write `status.json` back for legacy runs** — explicitly rejected in Q3; keep filesystem as audit log.
