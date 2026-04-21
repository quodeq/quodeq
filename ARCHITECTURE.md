# Architecture

## Layer Overview

| Layer | Purpose | Dependencies |
|-------|---------|--------------|
| `core/` | Domain logic: evidence models, scoring algorithms, standards definitions, type definitions | None (stdlib only) |
| `engine/` | Infrastructure and execution: pipeline orchestration, markers, runner utilities | core/, analysis/ |
| `data/` | Data access: filesystem repositories, web API clients, report parsers | core/ |
| `services/` | Business logic: dashboard, accumulated views, dismissals, standards CRUD | core/, data/ (via `services/ports.py`) |
| `api/` | HTTP layer: Flask routes, security, rate limiting | core/, services/ |
| `analysis/` | Evaluation pipeline: AI orchestration, subagents, prompts, MCP | core/, engine/, data/, services/ |
| `dashboard/` | Server/process management: build UI, start API, health checks | services/, api/ |
| `shared/` | Cross-cutting utilities: config, logging, env helpers | None (stdlib only) |
| `config/` | Configuration: paths, discipline detection, standards fetching | shared/ |

## Import Rules

```
core/          -> stdlib, core/ only
engine/        -> stdlib, core/, analysis/
data/          -> stdlib, core/
services/      -> stdlib, core/, data/ (via services/ports.py)
api/           -> stdlib, core/, services/
analysis/      -> stdlib, core/, engine/, data/, services/
dashboard/     -> stdlib, services/, api/
shared/        -> stdlib only
config/        -> stdlib, shared/
```

## File Size Guidelines (soft limits)

| Metric | Limit | Rationale |
|--------|-------|-----------|
| File lines | 100 | Fits in one context window |
| Function lines | 50 | Single-screen readable |
| Imports per file | 15 | Signals too many responsibilities |
| Functions per file | 12 | Beyond this, split the file |

## Conventions

- Private modules use `_` prefix (e.g., `_fs_projects.py`).
- Public APIs live in the parent `__init__.py` with re-exports for backward compatibility.
- Frozen dataclasses for data transfer objects.
- `services/ports.py` is the single boundary between services and data layers.

## Runtime State Model

Each evaluation has a directory under `~/.quodeq/evaluations/<project_uuid>/<run_id>/`. The files together describe the run's state; no single file is load-bearing.

### Per-run files

| File | Writer | Role |
|---|---|---|
| `status.json` | CLI (`shared/run_status.py`) | **Authoritative lifecycle state.** Atomic write-tmp-then-rename. Schema-versioned. |
| `.heartbeat` | CLI (`shared/run_heartbeat.py`) | Empty file whose mtime is the liveness signal. Touched every 5s while `state ∈ {running, finalizing}`. |
| `.pid` | CLI (`_cli_evaluation.py`) | OS PID. Used by the cancel flow (`services/_external_jobs.py`) to deliver SIGTERM. |
| `evidence/manifest.json` | Analysis engine | Scan inputs. Presence marks "a run was started." |
| `evidence/<dim>_evidence.jsonl` | Subagent pool | Per-dimension findings stream. |
| `evaluation/<dim>.json` | Scoring engine | Per-dimension report (the UI's "report" artifact). |
| `run.log` | CLI + dashboard subprocess | Verbatim stderr tee. Consumed by the live-terminal SSE endpoint and for historical replay. |
| `scan.json` | Report assembly | Aggregate report (legacy lifecycle signal; superseded by `status.json`). |

### Process-wide state

- **`~/.quodeq/index.db`** (SQLite, WAL) — one row per run. Mirrors `status.json` for fast dashboard queries. **Derived state** — delete at any time; rebuilt on next dashboard read via `services/run_index.sync_index`.
- **`JobManager`** (`services/jobs.py`) — in-memory registry of dashboard-spawned subprocesses. Authoritative for live progress of UI-started runs (log ring-buffer, phase markers). Per-process; evaporates on API restart.

## Lifecycle State Machine

```
pending ─► running ─► finalizing ─► done
            │            │
            ├────────────┴──────► failed     (exception)
            │            │
            └────────────┴──────► cancelled  (signal / atexit / stale-detected)
```

States defined in `shared/run_status.py::RunState`. Terminal states (`done`, `failed`, `cancelled`) are sticky — never re-entered.

**Guarantee matrix** (in `shared/run_lifecycle.py::RunLifecycleContext`):

| Exit cause | Final state | `exit_reason` |
|---|---|---|
| Normal completion | `done` | `null` |
| `AnalysisError` / `EvaluationError` | `failed` | `exception: <ClassName>` |
| SIGINT / SIGTERM / SIGHUP | `cancelled` | `signal_SIGINT` / `signal_SIGTERM` / `signal_SIGHUP` |
| atexit fallback | `cancelled` | `atexit_unfinalized` |
| SIGKILL / power-off | (uncatchable) → caught by heartbeat staleness | `stale_detected` |

Stale detection runs inside `services/_index_sync._check_stale_and_promote` during `sync_index`: if `state ∈ {running, finalizing}` AND `.heartbeat` > 30s old AND the PID is dead, the dashboard promotes to `cancelled(stale_detected)` by calling `write_status` on the run directory — so the resolution is durable across dashboard sessions.

## Data Flow — Dashboard Request

```
GET /api/evaluations
  → FilesystemActionProvider.list_evaluations
  → sync_index(db, evaluations_root)          (upsert changed rows, stale-check non-terminals)
  → list_runs(db) → [RunRow, ...]
  → _run_row_to_snapshot → [JobSnapshot, ...]
  → merge in-memory JobManager jobs           (dashboard-spawned live jobs override)
  → JSON response
```

## Data Flow — Live Terminal

```
Evaluator process (CLI or subprocess)
  ├─► stderr ────► run.log (tee via RunLogWriter + RunLogHandler)
  └─► stdout markers {"_cc": ...} ─► JobManager phase updates (filtered out of run.log)

Dashboard
  ├─► probes GET /api/jobs/<id>/logs?since=0  (404 → placeholder, skip SSE)
  └─► opens  GET /api/jobs/<id>/logs/stream   (SSE: replay + tail; `event: done` on terminal)
```

## Key Design Rules

1. **`status.json` is authoritative.** The index never holds state not derivable from `status.json` + filesystem signals. Delete `index.db` → next read rebuilds.
2. **PR evaluations don't write to the dashboard store.** The `quodeq-review.yml` workflow sets `--output $RUNNER_TEMP/quodeq-pr-eval`, so PR runs stay ephemeral. The dashboard's source of truth is nightly runs.
3. **Signal handlers in `RunLifecycleContext` cover every exit mode except SIGKILL.** SIGKILL + heartbeat staleness together close the loop.
4. **Legacy runs (pre-Plan-A, no `status.json`) are synthesized in the index only.** The filesystem is a pure audit log — we never mutate historical artifacts.

## Key Files (quick map)

| Concern | File |
|---|---|
| State machine | `src/quodeq/shared/run_status.py` |
| Heartbeat | `src/quodeq/shared/run_heartbeat.py` |
| Lifecycle context (signals + atexit + exc) | `src/quodeq/shared/run_lifecycle.py` |
| Run log writer | `src/quodeq/shared/run_log.py` |
| SQLite index + sync | `src/quodeq/services/run_index.py`, `_index_sync.py` |
| Provider (DB-backed) | `src/quodeq/services/filesystem.py` |
| In-memory jobs | `src/quodeq/services/jobs.py` |
| Live terminal SSE | `src/quodeq/api/_log_stream_routes.py` |
| Live terminal UI | `src/quodeq/ui/src/features/evaluation/components/LiveTerminal.jsx` |
