# Run Lifecycle Dashboard UI — Plan B2 Design Spec

**Status:** Draft
**Date:** 2026-04-21
**Author:** Victor + Claude (brainstorm)
**Builds on:** [2026-04-20-run-lifecycle-status-design.md](2026-04-20-run-lifecycle-status-design.md), [2026-04-21-run-lifecycle-dashboard-design.md](2026-04-21-run-lifecycle-dashboard-design.md)

## Problem

Plan A (#254) and Plan B1 (#255) are merged:
- Every run writes an authoritative `status.json` with explicit lifecycle + `exit_reason`.
- Dashboard `list_evaluations` / `get_evaluation_status` read from the SQLite index; stale runs are auto-promoted to `cancelled(stale_detected)`.

But the UI still reflects none of this richness:
- The "Source" badge still reads **"Running outside the dashboard"** for every external run — it was built for a time when the dashboard had no visibility into CLI-started runs. Now irrelevant.
- Every cancelled run looks identical in the status chip. A run cancelled by the user (Ctrl+C) reads the same as a run force-killed and promoted to `stale_detected` by the dashboard. Users can't distinguish "I cancelled this" from "our code crashed on us."
- Dead code remains in `_external_jobs.py` (`find_external_runs`, `_run_dir_to_snapshot`, `_infer_progress`) and `JobManager` (`_get_external`). All unreachable after Plan B1 rerouted the provider.

Plan B2 is small — three coordinated UI/backend changes that surface what Plan A/B1 already compute, plus a dead-code cleanup.

## Goals

1. The "External" badge shows only for genuinely external runs (CLI / CI / not in `JobManager` memory). Dashboard-spawned runs have no badge.
2. Cancelled runs visually distinguish **stale-promoted** (amber `"cancelled (stale)"`) from **user/signal/exception** (gray `"cancelled"` or red `"failed"`). A hover tooltip always exposes the raw `exit_reason`.
3. Remove the now-unreachable `find_external_runs` / `_run_dir_to_snapshot` / `_infer_progress` / `JobManager._get_external` code and the tests that exercise only them.

## Non-Goals

- "Rebuild Index" button in the dashboard (deferred — can curl `POST /api/index/rebuild` today; not user-pain-driven).
- Differentiating all cancel sub-reasons (user, signal, terminal close, atexit) in the chip text. Only `stale_*` gets a text qualifier. Others show the raw `exit_reason` in the tooltip.
- New `exit_reason` values — Plan A already defines the set. B2 consumes them.
- UI work for the `phase` / `current_dimension` fields — those are already surfaced by existing components.

## Architecture

Three coordinated changes, all small, landing in one PR.

### 1. Add `exit_reason` to `JobSnapshot`

`src/quodeq/core/types/job.py`:
```python
@dataclass(frozen=True, slots=True)
class JobSnapshot:
    ...
    source: str = "internal"
    exit_reason: str | None = None  # NEW
```

`src/quodeq/services/filesystem.py::_run_row_to_snapshot`:
```python
return JobSnapshot(
    ...
    source="external" if row.job_id.startswith("ext-") else "internal",
    exit_reason=row.exit_reason,  # NEW
)
```

`RunRow.exit_reason` already exists (populated by Plan B1's `_upsert_from_status`). This is pure plumbing.

### 2. UI changes in `EvaluationStatus.jsx`

- `ExternalRunBadge` — rewrite the JSX: text becomes `"External"`; rendered only when `job.source === 'external'` (the caller check at line 141 stays; the component simplifies).
- Extract `StatusChip` from the inline `<span>` at line 122. New component:
  ```jsx
  function StatusChip({ status, exitReason }) {
    const isStale = status === 'cancelled' && exitReason?.startsWith('stale_');
    const text = isStale ? 'cancelled (stale)' : status;
    const className = `job-status-badge ${status}${isStale ? ' job-status-badge--stale' : ''}`;
    return <span className={className} title={exitReason ?? ''}>{text}</span>;
  }
  ```
- `JobHeader` uses `<StatusChip status={job.status} exitReason={job.exitReason} />` in place of the raw span.

`EvaluationStatus.css` (or the nearest stylesheet):
```css
.job-status-badge--stale {
  background: var(--color-amber-bg, #422c0a);
  color: var(--color-amber-fg, #ffc864);
}
```

### 3. Dead-code deletion

**`src/quodeq/services/_external_jobs.py`** — delete:
- `find_external_runs` (lines 30-49)
- `_run_dir_to_snapshot` (lines 52-84)
- `_infer_progress` (lines 87-124)

**KEEP** (still used by the dashboard's cancel flow):
- `resolve_external_pid`
- `cancel_external_run`

If those two have internal dependencies on the deleted helpers, inline or refactor them.

**`src/quodeq/services/jobs.py`** — delete:
- `JobManager._get_external` (lines 194-204)
- `find_external_runs` import + branch inside `JobManager.list_jobs` (lines 227-228). With that branch gone, `list_jobs` returns only in-memory internal jobs.
- The `_get_external` call in `get_job` (line 187); `get_job` returns `None` for `ext-*` ids (the `FilesystemActionProvider.get_evaluation_status` override handles them via the index before reaching `JobManager`).

**`tests/services/test_external_jobs.py`** — remove tests for the deleted functions. Keep any tests exercising `resolve_external_pid` / `cancel_external_run`. If the file becomes empty of valid tests, delete it.

## Data Flow

No new flow — B2 is pass-through.

```
status.json write (Plan A) ─► sync_index (Plan B1) ─► RunRow.exit_reason (Plan B1)
  ─► _run_row_to_snapshot → JobSnapshot.exit_reason (B2)
  ─► to_camel_dict → JSON { exitReason }
  ─► <StatusChip exitReason={job.exitReason} /> renders amber "(stale)" or tooltip (B2)
```

## Error Handling

| Scenario | Behavior |
|---|---|
| `exit_reason` is `null` on a `done` run | Chip shows `"done"`, no tooltip. No regression. |
| `exit_reason` is `null` on a `cancelled` run (legacy data) | Chip shows `"cancelled"`, no qualifier, empty tooltip. |
| `exit_reason` is an unknown string (future code adds a new reason) | Chip falls back to `"cancelled"` + tooltip with the raw string. No crash. |
| `exit_reason === "exception: XyzError"` on a `failed` run | Chip shows `"failed"` + tooltip with the class. No amber (uses existing `failed` styling). |
| `source` field missing from JSON | `ExternalRunBadge` hidden (defaults to `undefined !== 'external'`). |
| `source === 'external'` on a dashboard-spawned run (shouldn't happen after B1) | Shows "External" badge wrongly — cosmetic, not broken. |
| Dead-code deletion misses a call site | `pytest -q` catches it. B1 E2E tests cover the real API chain. |
| `cancel_external_run` depends on a deleted helper | Grep first; keep or inline the helper as needed. |

## Testing

### Unit
- `tests/core/test_job_snapshot.py` — construct a `JobSnapshot` with `exit_reason="stale_detected"`, assert round-trip.
- `tests/api/test_snapshot_exit_reason.py` — `get_evaluation_status` on a seeded stale run returns a snapshot with `exit_reason="stale_detected"`.

### UI (Vitest)
Extend or create `tests/ui/.../EvaluationStatus.test.jsx` with four chip scenarios:
1. `status="done"` → `"done"`, no tooltip, no `--stale` class.
2. `status="cancelled", exitReason="stale_detected"` → `"cancelled (stale)"`, class includes `job-status-badge--stale`, tooltip `"stale_detected"`.
3. `status="cancelled", exitReason="signal_SIGTERM"` → `"cancelled"`, no `--stale` class, tooltip `"signal_SIGTERM"`.
4. `status="failed", exitReason="exception: EvaluationError"` → `"failed"`, no `--stale` class, tooltip `"exception: EvaluationError"`.

Plus `ExternalRunBadge` scenarios:
- `source="external"` → renders `"External"`.
- `source="internal"` → renders nothing.

### Regression
- All Plan B1 integration tests (`test_index_backed_provider.py`, `test_index_e2e.py`) still pass.
- `tests/services/test_external_jobs.py` tests that survived the deletion still pass.

### Manual smoke
- CLI run + `kill -9` → dashboard shows `cancelled (stale)` amber chip, tooltip "stale_detected".
- CLI run completed normally → "External" badge + green `done` chip.
- Dashboard-spawned run → NO badge, chip reflects live state.

## Rollout

Single PR targeting `develop`. After merge:
- The dashboard stops misleading users with "Running outside the dashboard" on every external run.
- Users can finally tell "I cancelled this" apart from "our code crashed on us" at a glance.
- ~100 lines of dead code + associated tests removed.

## Out of Scope

- **"Rebuild Index" button** — deferred; see follow-up below.
- **Fine-grained cancel sub-categorization** in the chip text (user/signal/terminal close/atexit). Only `stale_*` is called out by design — matches actual user-facing clarity need.
- **`source` field rescope to detect CI specifically** (e.g., `source="ci"`). Everything not in JobManager is "external"; refinement can come when a real need arises.
- **Badge styling overhaul** — keep the existing `.job-meta-value` styling for "External". No new fonts/colors.

## Follow-ups after B2

- Optional "Rebuild Index" button in the dashboard header, wired to `POST /api/index/rebuild`.
- Polish items from live-terminal review (I2: filter `_cc` JSON markers before teeing; I3: LiveTerminal placeholder + stop reconnect on 404; Task 1 race on `_disabled` / `close`).
- Profile `sync_index` at scale; memoize walks if first-open latency becomes noticeable.
