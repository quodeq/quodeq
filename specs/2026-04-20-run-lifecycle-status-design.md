# Run Lifecycle & Status — Design Spec

**Status:** Draft
**Date:** 2026-04-20
**Author:** Victor + Claude (brainstorm)

## Problem

Quodeq's dashboard infers run state from three implicit filesystem signals — `manifest.json` present + `scan.json` absent + `.pid` alive. When any of these diverge (force-killed CLI, crash before `scan.json` is written, stuck process that's alive but idle, GitHub Actions cancellation with no cleanup), the dashboard shows the run as "Evaluation in Progress" forever. The "Start Evaluation" button stays disabled. The user is stuck.

Root cause: there is no authoritative lifecycle record. State must be *deduced* from the presence/absence of files that were never designed as state signals. `scan.json` doubles as the results report AND the completion marker. `.pid` is used only for cancel, not for liveness detection. No heartbeat. No central index — the dashboard re-scans the filesystem on every poll.

## Goals

1. **A single authoritative state file per run** with explicit lifecycle transitions the dashboard reads (no more inference).
2. **Guaranteed terminal status** on every exit path except SIGKILL/power-off — Ctrl+C, `kill`, terminal close, unhandled exception, normal completion all write a terminal status.
3. **Stuck-process detection** — a heartbeat file whose absence-of-recent-touch identifies runs that are alive but not progressing.
4. **Fast dashboard queries** — a SQLite index that avoids re-scanning the filesystem on every poll.
5. **Backward compatible** with run directories created before this feature lands (don't force a migration).
6. **Fixes the `--dev --browser` mislabel** — "external vs dashboard-spawned" determination switches to JobManager membership, not filesystem inference.

## Non-Goals

- Streaming the full historical run list across machines or via network sync.
- Replacing `scan.json` as the report format; only its *lifecycle signal* role is deprecated.
- Re-architecting `JobManager`'s in-memory job state. It stays — the DB index becomes a persistent mirror.
- Implementing a `quodeq finalize-run` CLI subcommand (earlier "Option C" scope) — deferred until we see real CI need.
- Protecting against genuinely malicious tampering of `status.json` — this is a single-user desktop tool.

## Architecture

Three new pieces, two existing ones clarified.

### New per-run files (written by the CLI inside each `run_dir`)

- **`status.json`** — authoritative lifecycle state. Atomic write-temp-then-rename on every transition.
- **`.heartbeat`** — empty file. Its mtime is refreshed every 5s by a background thread while `state in {running, finalizing}`. Absence of recent touch = stale.
- *(existing)* **`.pid`** stays — used for SIGTERM during cancel.

### New process-wide index (managed by the API server)

- **`~/.quodeq/index.db`** — SQLite, WAL mode, single-user. One row per run. Rebuildable from filesystem at any time; index never holds authoritative state.

### Existing files with clarified roles

- **`scan.json`** — the REPORT (results schema owned by scoring engine). Its lifecycle-signal role is deprecated in favor of `status.json`.
- **`manifest.json`** — unchanged; input metadata.

### Control flow

```
CLI start
  ├─ mkdir run_dir
  ├─ write status.json {state: pending}
  ├─ install signal handlers (SIGINT, SIGTERM, SIGHUP), atexit, try/except
  ├─ write .pid
  ├─ start heartbeat thread (touches .heartbeat every 5s)
  ├─ transition: pending → running  (write status.json)
  │    └─ pool executes dimensions
  ├─ transition: running → finalizing
  │    └─ write scan.json, report dirs
  ├─ transition: finalizing → done
  │    └─ heartbeat thread stops, .pid unlinked (finally block)
  └─ process exits cleanly

On any terminal signal / exception:
  status.json → cancelled | failed
  heartbeat thread stops
  .pid unlinked
  process exits
```

```
Dashboard poll
  ├─ sync_index()  ─ O(N) fs stat + O(changed) upserts
  │    └─ for each run_dir: compare status.json mtime to DB row; upsert if changed
  │    └─ for each non-terminal row: stale check (heartbeat + PID) → promote to cancelled if stale
  └─ SELECT * FROM runs ORDER BY started_at DESC LIMIT ?  ─ O(log N) indexed query
```

## Lifecycle & `status.json` Schema

### States

`pending` → `running` → `finalizing` → `done` | `failed` | `cancelled`

### Allowed transitions

Any other transition is a bug that must raise in the helper module:

- `pending → running` (pool begins work)
- `running → finalizing` (pool done, reports being written)
- `finalizing → done` (reports completed)
- `running → failed` / `finalizing → failed` (unhandled exception)
- Non-terminal → `cancelled` (SIGINT/SIGTERM/SIGHUP, atexit unfinalized path, or stale-detection promotion)
- Terminal states (`done`, `failed`, `cancelled`) are sticky — never re-entered.

### File schema

```json
{
  "schema_version": 1,
  "job_id": "ext-<run_id>",
  "state": "running",
  "started_at": "2026-04-20T14:32:00+00:00",
  "updated_at": "2026-04-20T14:32:15+00:00",
  "finalized_at": null,
  "phase": "analyzing",
  "current_dimension": "security",
  "dimensions": ["security", "reliability", "maintainability"],
  "pid": 12345,
  "exit_reason": null
}
```

`exit_reason` values when state is terminal:
- `null` for `done`
- `user_cancel`, `signal_SIGINT`, `signal_SIGTERM`, `signal_SIGHUP`, `atexit_unfinalized`, `stale_detected`, `stale_legacy_pid_dead`, `stale_legacy_no_pid` for `cancelled`
- `exception: <ClassName>` for `failed`

### Atomic write

```python
def write_status(run_dir: Path, state: StatusDict) -> None:
    tmp = run_dir / "status.json.tmp"
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(run_dir / "status.json")  # POSIX-atomic on same fs
```

### Helper module

`src/quodeq/shared/run_status.py` owns the state machine, schema, atomic writes, and transition validation. CLI and dashboard both go through it — never hand-roll JSON.

## Heartbeat & Stale Detection

### Heartbeat writer (CLI)

A background thread in the CLI pool touches `.heartbeat` every 5 seconds while `state in {running, finalizing}`:

```python
def _heartbeat_loop(run_dir: Path, stop: threading.Event) -> None:
    heartbeat = run_dir / ".heartbeat"
    while not stop.is_set():
        try:
            heartbeat.touch()
        except OSError:
            pass  # best-effort; disk issues will surface via other paths
        stop.wait(5.0)
```

Started on `pending → running`. Stopped in the same `finally` block that writes the terminal `status.json`.

### Stale detection (dashboard)

During `sync_index()`, for any row with non-terminal `state`:

| `.heartbeat` mtime | PID | Action |
|---|---|---|
| < 30s ago | alive | leave as-is |
| < 30s ago | dead | promote to `cancelled(stale_detected)` — rare edge case |
| > 30s ago | alive | leave as-is — process may be doing slow work |
| > 30s ago | dead | promote to `cancelled(stale_detected)` |

The dashboard's promotion write goes through `run_status.write_status` — transitions remain auditable.

### Thresholds (env-tunable)

| Env var | Default | Purpose |
|---|---|---|
| `QUODEQ_HEARTBEAT_INTERVAL_S` | `5` | How often the CLI touches `.heartbeat` |
| `QUODEQ_HEARTBEAT_STALE_S` | `30` | Age above which dashboard considers heartbeat stale (6× interval) |

## Signal Handlers & Finalization

Three layers installed by `_run_pipeline_with_cleanup` — each catches a different failure mode.

### 1. Signal handlers

```python
def _install_signal_handlers(run_dir: Path) -> None:
    def _handle(signum, frame):
        name = signal.Signals(signum).name
        write_status(run_dir, state="cancelled", exit_reason=f"signal_{name}")
        raise SystemExit(128 + signum)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _handle)
```

Installed immediately after `run_dir` creation. Raises `SystemExit` so the enclosing `try/finally` runs (heartbeat stops, `.pid` unlinks).

### 2. atexit hook

```python
def _finalize_at_exit(run_dir: Path) -> None:
    current = read_status(run_dir)
    if current is None or current.state in TERMINAL_STATES:
        return
    write_status(run_dir, state="cancelled", exit_reason="atexit_unfinalized")
```

Registered with `atexit.register`. Covers any interpreter shutdown path that bypassed the explicit terminal writes.

### 3. Try/except around the pipeline body

```python
try:
    write_status(run_dir, state="running")
    # pipeline writes finalizing → done on success
except (AnalysisError, EvaluationError, Exception) as exc:
    write_status(run_dir, state="failed", exit_reason=f"exception: {type(exc).__name__}")
    raise
```

### Guarantee matrix

| Exit cause | Caught by | Final status |
|---|---|---|
| Normal completion | pipeline | `done` |
| Domain exception | try/except | `failed` |
| Programmer error | try/except | `failed` |
| SIGINT (Ctrl+C) | signal handler | `cancelled(signal_SIGINT)` |
| SIGTERM (kill) | signal handler | `cancelled(signal_SIGTERM)` |
| SIGHUP (terminal close) | signal handler | `cancelled(signal_SIGHUP)` |
| SIGKILL / power-off | uncatchable → heartbeat staleness | `cancelled(stale_detected)` |
| `sys.exit()` without terminal write | atexit | `cancelled(atexit_unfinalized)` |

## SQLite Index

### File

`~/.quodeq/index.db` — single-user, same home directory as `~/.quodeq/evaluations`. Opened in WAL mode for concurrent-reader-friendliness.

### Schema (v1)

```sql
CREATE TABLE runs (
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
    status_mtime      INTEGER NOT NULL  -- ns, used as dirty check
);
CREATE INDEX idx_runs_state      ON runs(state);
CREATE INDEX idx_runs_started_at ON runs(started_at DESC);

CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (1);
```

### Sync algorithm (lazy, dashboard-driven)

```python
def sync_index(db: sqlite3.Connection, evaluations_root: Path) -> None:
    for project_dir in evaluations_root.iterdir():
        if not project_dir.is_dir(): continue
        for run_dir in project_dir.iterdir():
            status_path = run_dir / "status.json"
            if not status_path.exists():
                _sync_legacy_run(db, run_dir)  # see Backward Compat
                continue
            status_mtime_ns = status_path.stat().st_mtime_ns
            cached = db.execute(
                "SELECT status_mtime FROM runs WHERE run_dir = ?", (str(run_dir),)
            ).fetchone()
            if cached and cached[0] == status_mtime_ns:
                _check_stale_and_promote(db, run_dir, status_path)
                continue
            _upsert_from_status(db, run_dir, status_path, status_mtime_ns)
    db.commit()
```

### Sync triggers

- `GET /api/evaluations` (list endpoint)
- `GET /api/evaluations/<id>` (detail endpoint — scopes sync to that one run_dir)
- `POST /api/index/rebuild` — drops and rebuilds the table (debugging / recovery)

### Migration

On every DB open, check `schema_version`. Lower than current → run scripted migrations sequentially. Higher → refuse to open (user upgrades Quodeq).

### Rebuild guarantee

Delete `index.db` at any time → next dashboard read rebuilds. Never authoritative.

## Backward Compatibility

Existing `run_dir`s have only `manifest.json` (+ maybe `scan.json`, maybe `.pid`). Legacy sync rule:

| Filesystem signals | Synthesized `state` | `exit_reason` |
|---|---|---|
| `scan.json` present | `done` | `null` |
| `scan.json` absent, `.pid` present, PID alive | `running` | `null` |
| `scan.json` absent, `.pid` present, PID dead | `cancelled` | `stale_legacy_pid_dead` |
| `scan.json` absent, `.pid` absent | `cancelled` | `stale_legacy_no_pid` |
| `manifest.json` absent | skip — not a run | — |

The synthesized row lives in SQLite only — no `status.json` is written back. Legacy runs stay legacy on disk; the index knows what they are.

**New runs always write `status.json` at `pending` first**, before any other artifact. From day one of the feature shipping, everything is first-class.

**The existing `find_external_runs` code is deprecated but not deleted in this PR** — kept as a fallback for debugging the transition. Next release removes it.

## Dashboard Integration

All existing `FilesystemActionProvider` methods reroute through the SQLite index.

| Method | New behavior |
|---|---|
| `list_evaluations(limit, reports_dir)` | `sync_index()`, then `SELECT ... ORDER BY started_at DESC LIMIT ?`. Map rows to `JobSnapshot`. |
| `get_evaluation_status(job_id, reports_dir)` | Scoped `sync_index()` for that `run_dir`, then `SELECT * FROM runs WHERE job_id = ?`. |
| `get_log_run_dir(job_id)` | `SELECT run_dir FROM runs WHERE job_id = ?`. Falls back to filesystem walk only if DB missing. |
| `is_job_complete(job_id)` | `SELECT state FROM runs WHERE job_id = ?` — complete iff `state IN ('done', 'failed', 'cancelled')`. Replaces the scan.json + PID heuristic. |

### UI-facing changes

- **`ExternalRunBadge` renamed and re-scoped.** If `JobManager` has the `job_id` in memory → "Dashboard-spawned". Otherwise → "External". Fixes `--dev --browser` mislabel by making JobManager membership (not filesystem detection) the authoritative check.
- **New status chip variant**: `cancelled (stale)` with subtle amber color. Hover tooltip shows `exit_reason`. Distinguishes "CI was force-killed" from "our code errored" (`failed`).
- **Live terminal component (previous branch) keeps working** — orthogonal to the index. `is_job_complete` routing becomes more reliable for it.

### Rate-limit considerations

`sync_index` is invoked inside already-rate-limited endpoints. Single-user local app → no external concurrent-writer concerns. WAL mode handles dashboard-reads-while-JobManager-writes.

## Error Handling

| Scenario | Behavior |
|---|---|
| `status.json` corrupt (invalid JSON) | Log warning, treat as legacy synthesis. Don't crash sync. |
| `status.json` `schema_version` > code version | Refuse to read that one run (warn user). Others unaffected. |
| `.heartbeat` touch fails (disk full, RO fs) | Silently caught. Thread keeps looping. |
| Cross-device `replace` (rare) | Fall back to direct write; partial file caught via JSON parse on read. |
| Signal arrives mid-`replace` | `replace` is atomic — never partial. Handler's own write wins via its own `replace`. |
| SQLite DB locked | Exponential backoff up to 3s; fall through on failure. Next poll retries. |
| SQLite DB corrupt | Delete file, rebuild. User sees "rebuilding index…" flash once. |
| Crash between terminal-state write and heartbeat thread stop | atexit stops thread. `.heartbeat` may touch once more — harmless (terminal state is sticky; stale detection ignores terminal states). |
| Dashboard promotes `cancelled` on a slow-but-alive CLI | Next CLI heartbeat + status write overwrites. Low-probability (30s window); acceptable. |

## Testing Strategy

### Unit tests

- **`tests/shared/test_run_status.py`** — state machine (all legal transitions, illegal ones raise), atomic write under concurrency, schema-version handling, corrupt-JSON read.
- **`tests/shared/test_heartbeat.py`** — thread touches on interval, stops on event, swallows `OSError`.

### Signal / lifecycle tests

- **`tests/ci/test_cli_signals.py`** — subprocess-spawned CLI, send SIGINT/SIGTERM/SIGHUP, assert `status.json` reads `cancelled(signal_*)`. Raise exception in pipeline → `failed`. Clean completion → `done`. `sys.exit()` path → `cancelled(atexit_unfinalized)`.

### Stale detection

- **`tests/services/test_stale_detection.py`** — matrix of heartbeat age × PID liveness × current state. Terminal states never promoted.

### Index

- **`tests/services/test_run_index.py`** — fresh DB + seeded fs populates; unchanged status_mtime skips upsert; schema migration v0→v1; concurrent readers under WAL; delete DB → rebuild on next sync.

### Backward compat

- **`tests/services/test_legacy_run_sync.py`** — all rows of the legacy synthesis matrix.

### Integration

- **`tests/ci/test_status_lifecycle_e2e.py`** — full dry-run CLI, poll `status.json`, assert full transition sequence. Cancel mid-run via SIGTERM → final `cancelled(signal_SIGTERM)`.
- **`tests/api/test_index_backed_provider.py`** — `GET /api/evaluations` returns correct rows for fresh + legacy + stale + terminal runs.

## Out of Scope

- `quodeq finalize-run` CLI subcommand for CI `always()` hooks. Deferred — heartbeat staleness covers the force-kill case adequately.
- Per-dimension sub-states. Current `phase` + `current_dimension` fields are sufficient.
- Network sync of the index across machines.
- Migrating evidence JSONL files into the DB. They stay on the filesystem where they belong (large, append-only).
- Replacing `JobManager` with a DB-backed implementation. Index mirrors JobManager; JobManager stays authoritative for in-flight dashboard-spawned runs.
- Protecting against malicious tampering of `status.json`.
