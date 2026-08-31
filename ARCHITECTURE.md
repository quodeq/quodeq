# Architecture

## Layer Overview

| Layer | Purpose | Dependencies |
|-------|---------|--------------|
| `core/` | Domain logic: evidence models, scoring algorithms, standards definitions, type definitions, stream-event parsing | None (stdlib only) |
| `data/` | Data access: filesystem repositories, web API clients, report parsers | core/ |
| `services/` | Business logic: dashboard, accumulated views, dismissals, standards CRUD | core/, data/ |
| `assistant/` | Embedded LLM assistant: sessions, tool registry, provider turn adapters, guard | core/, data/, services/, llm_bridge/ |
| `api/` | HTTP layer: Flask routes, security, rate limiting | core/, services/, update/, assistant/, llm_bridge/ |
| `analysis/` | Evaluation pipeline: AI orchestration, subagents, prompts, MCP, markers, scoring pipeline | core/, data/, services/, context/ |
| `dashboard/` | Server/process management: build UI, start API, health checks | services/, api/, update/ |
| `llm_bridge/` | LLM provider bridge: Ollama, OpenRouter, CLI-tool providers | (nothing — leaf; one grandfathered analysis import) |
| `terminal/` | Embedded-terminal PTY backends (Unix pty / Windows ConPTY) + manager | core/ |
| `update/` | Update-notification subsystem (notify-only; never self-replaces the binary) | None |
| `ci/` | CI integration: report posting, evidence reading, SARIF export | core/, services/, analysis/, context/ |
| `context/` | Context enrichment: path-role classification, project shape, precedent fingerprinting | core/, data/, llm_bridge/ |
| `ui/` | React + Vite dashboard frontend (npm project, served by the Flask API) | n/a (JavaScript) |
| `shared/` | Cross-cutting utilities: config, logging, env helpers | core/ (pure helper re-exports) |
| `config/` | Configuration: paths, discipline detection, standards fetching | shared/ |

## Import Rules

```
core/          -> core/
data/          -> core/
services/      -> core/, data/
assistant/     -> core/, data/, services/, llm_bridge/
api/           -> core/, services/, update/, assistant/, terminal/, llm_bridge/
analysis/      -> core/, data/, services/, context/
dashboard/     -> services/, api/, update/
terminal/      -> core/
update/        -> (nothing)
context/       -> core/, data/, llm_bridge/
shared/        -> core/ (strict — no cross-cutting blanket)
llm_bridge/    -> (nothing)
ci/            -> core/, services/, analysis/, context/
```

Every checked layer may additionally import stdlib plus the cross-cutting
`shared/` and `config/` packages. Only `ui/` (JavaScript) and package-root
modules (`cli.py`, `_cli_*.py`) are outside the checker. `core/` and `shared/`
are strict: the cross-cutting allowance does not apply to them.

These rules are enforced in CI by `tools/check_imports.py` via `tests/tools/test_import_layers.py`.
Pre-existing violations are grandfathered in `tools/import_baseline.txt` (a burn-down list, currently
6 entries: fix imports rather than add entries). Regenerate the baseline only with justification:
`python tools/check_imports.py --update-baseline`.

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
- `services/ports.py` and `services/_wiring.py` are the single boundary between services and data layers, split by role: `ports.py` hosts only the Protocols services accept as injected seams (`StandardsStore`, `GradeTablesReader`, re-exported from `data/ports/`) and boundary error types; `_wiring.py` is the composition/default-binding module, re-exporting the concrete data-layer functions services use. Services import their types from `ports.py` and their defaults from `_wiring.py`, so a storage swap touches `_wiring` + `data/`, never `ports` consumers. `tools/check_imports.py` allows any services→data import — this is a convention, not an enforcement point — but new or edited services code imports through `_wiring.py` (or `ports.py` for Protocols).
- Ports for concrete adapters live in `data/ports/` (`FindingsRepository`, `AssistantStore`, `ActionLog` — mirrors `data/actions_log.py::ActionLogWriter`, `DismissedSnippetsReader` — a `Callable` alias mirroring `data/sqlite/findings_queries.py::read_dismissed_snippets`, `EventEmitter` — protocol for appending run events; injected into `analysis` orchestration instead of directly constructing `data/events/writer.py::EventLogWriter`, `StoreUnreadableError` — error type raised by adapters when the state store is unreadable; lives here so `services/ports.py` can import without coupling to a concrete adapter); consumers annotate against the Protocol, composition roots construct the SQLite classes.
- Entities in `core/` are plain frozen dataclasses (stdlib only). Serialization lives in adapters: the event-log JSON codec is `data/events/codec.py`, dict→dataclass mappers are `data/mappers/`, the API wire serializer (`to_camel_dict`) is `shared/serialization.py`, and env-derived settings are resolved in `config/` (e.g. `config/evidence_env.py`, `config/clone_env.py`, `config/analysis_env.py`, `config/standards_env.py`) and passed inward as parameters. `tests/tools/test_serialization_boundary.py` ratchets `to_camel_dict` use to `api/` plus a declared list of other wire boundaries.
- Inner layers (`core/`, `analysis/`, `services/`, `config/`) accept an injected `core/observability.py::LogSink` instead of importing a logging framework directly; the default is the silent `NULL_LOG`, and composition roots (CLI, api, dashboard) pass a real sink, e.g. `shared/log_sink.py::SHARED_LOG`. `tests/tools/test_logging_boundary.py` ratchets new `logging`/`shared.logging` imports in those four directories against a declared, burn-down-only list.
- Fire-and-forget background work (a route handler kicking off salvage-scoring, a mutation flow's projection fallback) goes through `services/background.py`'s `BackgroundRunner` protocol (default `ThreadBackgroundRunner`, one daemon thread per submission) instead of each call site spawning its own thread.
- Score-cache persistence lives in `data/sqlite/` (`score_cache_store.py`, `score_cache_db.py`, `_score_cache_epoch.py` — moved from `services/`, keeping SQL access behind the data layer).
- `dashboard/_probes.py` bundles the API-startup path's collaborators (`ApiProbes`, `DashboardHooks`, `NativeShell`) as frozen dataclasses defaulting to the production implementation, so tests inject fakes instead of patching module attributes. `NativeShell` (`webview_importable`, `linux_backend_available`, `make_instance`, `spawn_window`, `open_browser`) is `_serve_native`'s collaborator seam in `dashboard/_server.py`, taken via a `shell=` kwarg; `_serve_native` and `_serve_blocking` also take an injectable `serve_blocking=` kwarg.
- `data/fs/` gained a few narrowly-scoped adapters for facts that used to be computed ad hoc: `evidence_tally.py` (unique finding counts from a dim's raw evidence JSONL, shared by the subagent-pool heartbeat and the dashboard's live scan-progress reader), `git_stats.py` (read-only `git log` commit counts, fails open to `None` on any git trouble), and `project_index.py` (the public facade over the project-identity index's internal `_index_io`/`_models`/`_resolution` split).
- `data/fs/dimension_report/` builds and persists per-dimension report files (split into `_report_constants.py`, `_report_scoring.py`, `_report_findings.py`, `_report_assembly.py`, `_report_io.py` for disk persistence); `analysis/report.py` and its sibling `analysis/_report_*.py` modules re-export the package's public names as shims so pre-existing import paths stay live. The reader counterpart lives at `data/fs/report_parser/`.
- `data/cache_store/` is the result-cache filesystem adapter: `entry.py` (`CacheEntry`, the persisted record for one key), `backend.py` (`CacheBackend` protocol + `CacheStats`), `local.py` (`LocalFileBackend`, the sharded filesystem implementation, cache root resolved via `QUODEQ_CACHE_ROOT` mirroring `context/online_cache.py`). `analysis.cache.{entry,backend,local}` re-export it as shims; the analysis-internal cache machinery (key derivation, dispatch, tiered/gc policy) stays in `analysis/cache/`.
- `data/cli_models.py` (`run_cli_models_command`) and `data/anthropic_models.py` (`fetch_anthropic_models`) are the two AI-tooling discovery adapters: `data/cli_models.py` owns the CLI `/models` subprocess boundary, `data/anthropic_models.py` owns the Anthropic HTTP boundary. `services/tooling_mixin.py` keeps the policy (client allowlist, key/URL/timeout resolution, fallback behavior) and calls both via `services/_wiring.py`.
- Process-tree termination (`kill_tree`, `terminate_process`) lives in `shared/_process_kill.py`, a cross-cutting helper shared by `services/jobs.py`, `services/_external_jobs.py`, and the assistant/terminal layers, so no layer reimplements SIGTERM/SIGKILL-then-`taskkill` escalation. `services/_external_jobs.py::ProcessControl` (frozen dataclass: `kill_tree`, `pid_alive`) is the injectable seam `cancel_external_run` takes via a `control=` kwarg, threaded through `services/jobs.py::JobManager(process_control=)`.
- `shared/cancellation.py::CancellationToken` wraps a `threading.Event` plus a first-writer-wins reason string; the module-level `is_cancelled()`/`request_cancel()`/`get_event()` facade delegates to a process-wide `_DEFAULT` instance (the SIGTERM/SIGINT handler in `run_lifecycle` cannot receive an injected token, so a default instance is the composition seam, same shape as `SHARED_LOG`). Tests construct their own `CancellationToken()` instead of resetting global state.
- Route business logic keeps moving into `services/` use cases with the route left as request parsing and response shaping, e.g. `services/shared_connect.py` (connect/validate/clone a shared-results repo, extracted from `PUT /api/shared/config`) and `services/standards_overrides.py` (per-project override count/diff analysis, extracted from `api/standards_overrides_routes.py`).

## Runtime State Model

Each evaluation has a directory under `~/.quodeq/evaluations/<project_uuid>/<run_id>/`. The files together describe the run's state; no single file is load-bearing.

### Per-run files

| File | Writer | Role |
|---|---|---|
| `status.json` | CLI (`shared/run_status.py`) | **Authoritative lifecycle state.** Atomic write-tmp-then-rename. Schema-versioned. |
| `.heartbeat` | CLI (`shared/run_heartbeat.py`) | Empty file whose mtime is the liveness signal. Touched every 5s while `state ∈ {running, finalizing}`. |
| `.pid` | CLI (`_cli_evaluation.py`) | OS PID. Used by the cancel flow (`services/_external_jobs.py`) to deliver SIGTERM. |
| `evidence/manifest.json` | Analysis engine | Scan inputs. Presence marks "a run was started." |
| `evidence/<dim>_evidence.jsonl` | Subagent pool (via `analysis/mcp/router.py::FindingsRouter`) | **Durable findings log.** Append-only stream, source of truth. JSONL is human-readable, recoverable from any disk, and never deleted by the system. |
| `events.jsonl` | Analysis MCP server (`analysis/mcp/findings_server.py`) + mutation services (dismiss/verify) via `data/events/writer.py::EventLogWriter` | **Event Log.** Append-only stream of typed events (`RUN_STARTED`, `JUDGMENT_CREATED`, `FINDING_DISMISSED`, …) defined in `core/events/models.py`. |
| `evaluation.db` | Projection layer (`data/projection/projector.py::Projector` → `data/sqlite/findings_repository.py::SqliteFindingsRepository`) | **State Store: indexed projection of the Event Log.** SQLite + FTS5. Reads self-ensure the store is fresh against `events.jsonl` before returning rows; `services/_post_run_hook.py` also projects when a JobManager job finishes. Deleted-or-absent → rebuilt from the Event Log; loader falls back to JSONL/JSON. Set `QUODEQ_DISABLE_SQLITE=1` to skip both the write and the read for instant rollback. |
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

## Deterministic Requirement Checkers

Some requirements are properties of the whole codebase rather than of any one
file — "no transitive framework dependencies in core layers" cannot be judged
by reading a single file, which is why they never produced a judgment at all.
A requirement opts into a deterministic checker by naming it in the compiled
standard:

```json
{ "id": "CLEA-DEP-06", "text": "...", "check": "framework-imports" }
```

At run time `analysis/checks/runner.py` resolves the named checkers, runs each
once, filters the judgments back to the requirements that declared it, and
folds the results into the dimension's evidence — as ordinary violations and
compliances, so scoring, dismissal, the dashboard and the SQL projection need
no special case. A checker that runs clean emits **one** compliance, because
"no violations" and "never checked" must not look the same.

Three rules hold everywhere in this path:

- **Fail-soft.** A checker that raises, a standard that will not parse, a JSONL
  that will not open — each costs the deterministic findings and nothing else.
- **Forward compatible.** A `check` name this build does not know is skipped,
  not an error: standards ship as data and outlive binaries.
- **Never cached.** These are graph properties, and the per-file content cache
  has no key that could express "the graph changed". They recompute per run.

| Piece | File |
|---|---|
| Pure judgment logic | `src/quodeq/core/checks/` |
| Static facts off disk (the only I/O) | `src/quodeq/data/fs/import_graph.py`, `symbol_uses.py` |
| Registry + fact memo + run wiring | `src/quodeq/analysis/checks/` |

Shipped checkers, and the requirements they answer:

| `check` | Requirements |
|---|---|
| `framework-imports` | CLEA-FRM-01, CLEA-DEP-06 |
| `entity-imports` | CLEA-DEP-02 |
| `config-reads` | CLEA-DEP-07 |

Adding one is: a pure function in `core/checks/` returning `Judgment`s, an entry
in `CHECKERS`, and a `"check"` key on the requirement. New facts (beyond the
import graph and symbol uses) get their own collector in `data/fs/` and a lazy
accessor on `CheckContext`, which memoises per context so several checkers
share one walk of the tree.

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
| Live terminal SSE | `src/quodeq/api/_log_stream_routes.py`, `_sse_log_helpers.py` |
| Live terminal UI | `src/quodeq/ui/src/features/evaluation/components/ConsoleLogViewer.jsx` + `eval-log/useJobLogStream.js` |
| Event Log → State Store projection | `src/quodeq/data/projection/projector.py`, `src/quodeq/data/sqlite/findings_repository.py` |
