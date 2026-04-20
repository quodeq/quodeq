# Live Terminal Stream — Design Spec

**Status:** Draft
**Date:** 2026-04-20
**Author:** Victor + Claude (brainstorm)

## Problem

The dashboard's view of a running evaluation is coarse and asymmetric with the CLI experience:

- **CLI** (`quodeq evaluate`) streams rich stderr output line-by-line: phase transitions, dimension progress, violation counts, timestamps. The user sees every heartbeat.
- **Dashboard-spawned run** captures subprocess stdout/stderr into `Job.logs` (a ~100-line ring buffer), polled by the UI every 1500ms via `GET /api/evaluations/<id>`. Lines are lost once the buffer rotates; granularity is coarse; ANSI stripped.
- **Externally-started run** (CLI in another terminal, CI runner) gets worse treatment — the UI detects it via `find_external_runs` ([_external_jobs.py:30](../src/quodeq/services/_external_jobs.py:30)) scanning the filesystem for `manifest.json` + absence of `scan.json`, infers phase/dimension from artifact file counts, and explicitly renders the message "Live logs unavailable for external runs — progress inferred from filesystem."

The user's summary: "Running outside the dashboard is entirely bad implemented." The dashboard feels like it's watching a filesystem rather than an evaluation. The goal is to make the dashboard show the evaluation *fully, as if executed from the terminal*, regardless of who started it.

## Goals

1. Any evaluation running on this machine streams live into any open dashboard. CLI-started, dashboard-started, CI-started — all the same UX.
2. Opening the dashboard on a running job replays the full log from the first line, then tails. No "tune in mid-show" limitation.
3. Opening the dashboard on a completed job replays the same terminal output it showed live. Historical parity.
4. The transport is simple enough that a single developer can debug it with `tail -f` and `curl`.
5. Producer cost is trivial — adding log streaming must not risk crashing an evaluation.

## Non-Goals

- Bidirectional terminal (no REPL / stdin). The UI is read-only.
- Multi-machine fan-out. One machine, one or more dashboards on the same machine.
- Structured event envelopes. Raw stderr is the format; the UI renders it verbatim via xterm.js.
- Concurrent evaluations. In practice only one runs per machine at a time; the design does not rely on this, but does not optimize for N>1 either.
- Replacing the existing status card. The structured status polling stays; the terminal view is additive.

## Architecture

```
                   ┌──────────────────────────────┐
                   │   Evaluation process          │
                   │   (CLI or subprocess)         │
                   │                               │
                   │   log_info → stderr           │
                   │            → RunLogWriter     │
                   └──────────────┬────────────────┘
                                  │ append + flush
                                  ▼
                   ┌──────────────────────────────┐
                   │   {run_dir}/run.log          │
                   │   (plain text, line-buffered)│
                   └──────────────┬────────────────┘
                                  │ tail by byte-offset
                                  ▼
                   ┌──────────────────────────────┐
                   │   GET /api/jobs/<id>/logs/…  │
                   │   SSE  (+ plain JSON)         │
                   └──────────────┬────────────────┘
                                  │ EventSource
                                  ▼
                   ┌──────────────────────────────┐
                   │   <LiveTerminal /> (xterm.js) │
                   │   inline in EvaluationStatus  │
                   └──────────────────────────────┘
```

Every evaluation run writes its stderr stream verbatim to `{run_dir}/run.log`, alongside the existing `manifest.json` / `evidence/` artifacts. The run directory remains the single source of truth. A new SSE endpoint tails the file and pushes lines to the dashboard. The UI renders them in an xterm.js pane embedded below the existing status card.

## Components

Five units, one responsibility each.

### 1. `RunLogWriter` (new)
**File:** `src/quodeq/shared/run_log.py`

Minimal file-handle wrapper.

```python
class RunLogWriter:
    def __init__(self, run_dir: Path): ...
    def write(self, line: str) -> None:
        """Append a single line to run.log. Catches and swallows errors."""
    def close(self) -> None: ...
```

- Opens `{run_dir}/run.log` in append + line-buffered mode.
- `write` normalizes line endings (always `\n`), flushes after each line.
- On any `OSError` (disk full, permissions), logs once to real stderr and becomes a no-op. Never raises to the caller.
- Used by both the CLI path and the subprocess dispatcher.

### 2. CLI producer hook
**Files:** `src/quodeq/_cli_evaluation.py`, `src/quodeq/shared/logging.py`

Route all `log_info(...)` / stderr prints through `RunLogWriter` in addition to real stderr (tee). Install the writer once `run_dir` is known (after `_setup_run_dirs`). Tear down in the same `finally` block that writes `scan.json`.

No format changes. Just duplication to the file.

### 3. Dashboard-spawned producer hook
**File:** `src/quodeq/services/jobs.py` (modify `_consume_stream`, ~line 116)

The subprocess output already streams through `_consume_stream`. Add a `RunLogWriter.write(line)` call alongside the existing ring-buffer append. ANSI codes are already stripped upstream — leave that behavior.

Writer lifetime matches the job's process lifetime.

### 4. SSE + plain endpoints (new)
**File:** `src/quodeq/api/_log_stream_routes.py`

Two routes:

- `GET /api/jobs/<id>/logs/stream` — Server-Sent Events.
  - Resolves `<id>` → `run_dir` via the same provider method the status card uses (handles internal `JobManager` IDs and `ext-<run_id>` prefixes uniformly).
  - Opens `{run_dir}/run.log`, starts at `Last-Event-ID` byte-offset if provided else `0`.
  - Streams existing contents, then polls file size every 100ms, emits new bytes as `data:` frames with `id: <byte-offset>`.
  - Detects job completion via `get_evaluation_status(job_id).status in ("done", "failed", "cancelled")`. On completion: flush remaining bytes, send `event: done`, close.
  - On missing log file: `retry: 1000`, poll up to 10s for file to appear. After that: 404.
  - On missing `run_dir`: 410 Gone.

- `GET /api/jobs/<id>/logs?since=<byte_offset>` — Non-streaming fallback.
  - Returns `{"lines": [...], "nextOffset": N, "done": bool}` snapshot.
  - Same resolution + error semantics as the SSE route.
  - Useful for initial replay on very slow connections and for tests.

Registered via `register_all_routes` alongside existing log routes; protected by the same `@require_auth` decorator and before_request middleware.

### 5. UI terminal pane (new)
**Files:**
- `src/quodeq/ui/src/features/evaluation/components/LiveTerminal.jsx` (new)
- `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.jsx` (modify — embed `<LiveTerminal>` below the existing status card)
- `src/quodeq/ui/package.json` (add `xterm`, `xterm-addon-fit`)

`<LiveTerminal jobId={...} completed={bool}>`:
- Creates an xterm.js `Terminal` instance, mounts on an internal `<div ref>`.
- Opens `new EventSource('/api/jobs/' + jobId + '/logs/stream')`.
- On `message` event: `term.write(event.data + '\r\n')`.
- On `event: done`: closes EventSource, disables reconnect. Scrollback stays.
- On unmount: closes EventSource, disposes terminal.
- Collapsible: wrapper renders a header `▾ Terminal (N lines)` / `▸ Terminal` with click to toggle; collapsed state hides the xterm DOM but keeps state (instance not disposed).
- For completed runs, same component: EventSource replays from offset 0, server sends `event: done` immediately after full file dump, connection closes.

## Data Flow

### Write path
```
log_info(line) / subprocess stderr
    → (existing) real stderr or Job.logs ring buffer
    → (new) RunLogWriter.write(line) → O_APPEND write + flush
```
Write happens on the producer thread, synchronously. Line-buffered flush ensures readers see lines within milliseconds.

### Read path
```
UI mounts <LiveTerminal jobId={id} />
  → EventSource('/api/jobs/<id>/logs/stream')
  → server resolves id → run_dir
  → server opens run.log, sends bytes from offset 0 (or Last-Event-ID)
  → server poll-loop (100ms): on file growth, reads new bytes, emits SSE events with id:<new-offset>
  → server detects job.status in terminal state → sends event: done → closes
```

### Resolution
`<id>` can be internal (`JobManager._jobs`) or external (`ext-<run_id>`). The SSE route calls the existing status resolver (same path the status card uses) to get `run_dir`. No new resolution logic.

### Multi-viewer
Each EventSource connection is independent — own file handle, own poll loop. No shared server state. Bounded by open dashboard tabs (realistically 1-3).

## Error Handling

| Scenario | Behavior |
|---|---|
| `run.log` not yet created | SSE sends `retry: 1000`, polls for up to 10s, then 404. |
| `run_dir` deleted mid-stream | 410 Gone; UI shows "run artifacts removed." |
| Job completes while viewer connected | Server sends final `event: done`; UI stops EventSource; scrollback intact. |
| Disk full / permission denied on write | `RunLogWriter.write` logs once to stderr, becomes no-op. Run never crashes because the log file cannot be written. |
| Reader reads mid-line (no `\n` yet) | Server holds partial tail in local buffer; appends on next poll. Client sees whole lines only. |
| EventSource reconnect after network hiccup | Browser sends `Last-Event-ID: <byte-offset>`; server seeks to `offset + 1`, resumes. No duplicates or gaps. |
| Concurrent writers (defensive) | `O_APPEND` — kernel serializes writes. Never corruption, at worst interleaved lines. |

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `QUODEQ_LOG_STREAM_POLL_MS` | `100` | Server-side poll interval for new bytes |
| `QUODEQ_LOG_STREAM_MAX_WAIT_S` | `10` | How long SSE waits for run.log to appear |
| `QUODEQ_LOG_FILE_NAME` | `run.log` | File name under run_dir (escape hatch for packaging) |

No user-facing UI toggle. The terminal pane is always embedded; user collapses it if they don't want it.

## Retention

`run.log` lives inside the existing run directory forever — same lifetime as `manifest.json`, `evidence/`, and `scan.json`. Deleted only when the user deletes the run via existing cleanup flows. Plain text; typical size KB to low MB. No compression or rolling.

This enables historical replay: opening an old evaluation in the dashboard shows its original terminal output via the same `LiveTerminal` component — server replays the file then sends `done`.

## UI Placement

Inline, under the existing status card on `EvaluationStatus.jsx`:

```
┌─ Evaluation Status ──────────────────────┐
│ Phase: Analyzing · Dimension: security   │
│ [tag tag tag]                            │
│ Findings: 12 · Compliance: 48            │
└──────────────────────────────────────────┘
┌─ ▾ Terminal (342 lines) ─────────────────┐
│ > Starting evaluation (may take …)       │
│ > Report path: /Users/…/evaluations/…    │
│ > → [1/3] Analyzing security | 0m12s     │
│ > ...live tail...                        │
└──────────────────────────────────────────┘
```

Structured status (top) is driven by existing snapshot polling. Terminal pane (bottom) is the new live stream. Both update independently.

## Testing

- **`tests/shared/test_run_log.py`** — `RunLogWriter` unit tests: append, byte offsets, silent failure when dir missing, line-buffered flush (read-after-write visibility).
- **`tests/api/test_log_stream_routes.py`** — SSE + plain endpoint tests: `text/event-stream` content type; initial replay contains seeded lines with correct `id:` offsets; partial-line handling (seed file without trailing newline, append rest, assert no duplicate/split lines); `Last-Event-ID` resume correctness; 404 on missing file; 410 on missing run_dir.
- **`tests/ci/test_run_log_integration.py`** — End-to-end CLI: spawn `quodeq evaluate` against a tiny fixture repo, assert `run.log` exists in `run_dir`, contains expected progress markers.
- **`tests/services/test_jobs_run_log.py`** — Dashboard path: stub subprocess prints scripted sequence; assert `_consume_stream` tees every line to `run.log` while preserving the existing `Job.logs` ring buffer.
- **`tests/ui/features/evaluation/LiveTerminal.test.jsx`** (Vitest) — mount `<LiveTerminal>`, mocked EventSource pushes lines, assert xterm buffer receives them in order; `done` event closes without clearing scrollback.
- **Smoke test** (optional) — run a tiny real evaluation, open a Flask test-client SSE connection concurrently, assert streamed lines match the stderr from the process.

## Out of Scope

- Switching existing status-card polling to SSE. The structured status endpoint stays as-is.
- Streaming to remote dashboards (different machine). Requires separate transport/auth design.
- Input (REPL) from terminal view. Read-only.
- Pruning old `run.log` files. Cleanup rides on existing run-directory cleanup.
