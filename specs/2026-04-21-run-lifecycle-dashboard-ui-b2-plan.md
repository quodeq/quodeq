# Run Lifecycle Dashboard UI — Plan B2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface `exit_reason` in the dashboard so users can distinguish stale-promoted cancellations from user/signal/exception cancellations; replace the obsolete "Running outside the dashboard" badge with a concise "External" label; delete now-unreachable legacy detection code.

**Architecture:** Plumb `exit_reason` through `JobSnapshot` and the provider mapper. Rewrite `ExternalRunBadge` and extract a `StatusChip` helper in the React dashboard. Delete `find_external_runs`, `_run_dir_to_snapshot`, `_infer_progress`, and `JobManager._get_external` (unreachable after Plan B1 rerouted through the SQLite index).

**Tech Stack:** Python 3.12 (dataclass), React 18 + Vite, Vitest, pytest.

See spec: [2026-04-21-run-lifecycle-dashboard-ui-b2-design.md](2026-04-21-run-lifecycle-dashboard-ui-b2-design.md).

## File Structure

**Modified (backend):**
- `src/quodeq/core/types/job.py` — add `exit_reason` field to `JobSnapshot`.
- `src/quodeq/services/filesystem.py` — pass `exit_reason` in `_run_row_to_snapshot`.
- `src/quodeq/services/jobs.py` — delete `_get_external`, simplify `get_job` / `list_jobs`.
- `src/quodeq/services/_external_jobs.py` — delete `find_external_runs`, `_run_dir_to_snapshot`, `_infer_progress`, `_pid_liveness`, `_is_pid_alive`, `_manifest_started_at`. Keep `resolve_external_pid`, `cancel_external_run`.

**Modified (UI):**
- `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.jsx` — rewrite `ExternalRunBadge`, extract `StatusChip`.
- `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.css` (or nearest stylesheet owning `.job-status-badge`) — add `.job-status-badge--stale`.

**Deleted tests:**
- `tests/services/test_external_jobs.py` — tests covering deleted functions. Keep tests for `resolve_external_pid` / `cancel_external_run` (delete the file if nothing else remains).

**New/modified tests:**
- `tests/api/test_snapshot_exit_reason.py` (new).
- `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.test.jsx` (new or extend existing).

## Branch

Already on `feat/run-lifecycle-dashboard-ui-b2` off `origin/develop` (which contains Plans A + B1 + live-terminal merged). Spec commit is `736cfdf0`.

---

## Task 1: Add `exit_reason` to `JobSnapshot` + provider pass-through

**Files:**
- Modify: `src/quodeq/core/types/job.py`
- Modify: `src/quodeq/services/filesystem.py` (`_run_row_to_snapshot`)
- Test: `tests/api/test_snapshot_exit_reason.py`

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_snapshot_exit_reason.py
"""exit_reason should round-trip from status.json → DB → provider → JobSnapshot."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from quodeq.shared.run_status import RunState, write_status


def _seed_stale_run(reports: Path, project: str, run_id: str) -> Path:
    d = reports / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    # status.json with running state + dead PID; heartbeat 60s old → sync_index
    # will promote to cancelled(stale_detected).
    write_status(d, state=RunState.RUNNING, job_id=f"ext-{run_id}",
                 started_at="2026-04-20T00:00:00+00:00", dimensions=[], pid=999999999)
    heartbeat = d / ".heartbeat"
    heartbeat.touch()
    old = time.time() - 60
    os.utime(heartbeat, (old, old))
    return d


def test_jobsnapshot_has_exit_reason_field() -> None:
    from quodeq.core.types.job import JobSnapshot
    snap = JobSnapshot(
        job_id="ext-x", status="cancelled", exit_reason="stale_detected",
    )
    assert snap.exit_reason == "stale_detected"


def test_jobsnapshot_exit_reason_defaults_to_none() -> None:
    from quodeq.core.types.job import JobSnapshot
    snap = JobSnapshot(job_id="x", status="done")
    assert snap.exit_reason is None


def test_provider_snapshot_surfaces_stale_exit_reason(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_stale_run(reports, "p", "stale-run")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    snap = provider.get_evaluation_status("ext-stale-run", reports_dir=reports)
    assert snap is not None
    assert snap.status == "cancelled"
    assert snap.exit_reason == "stale_detected"


def test_provider_list_surfaces_exit_reason(tmp_path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    _seed_stale_run(reports, "p", "stale-one")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))

    from quodeq.services.filesystem import FilesystemActionProvider
    provider = FilesystemActionProvider(index_db_path=tmp_path / "idx.db")
    jobs = provider.list_evaluations(limit=0, reports_dir=reports)
    stale = next((j for j in jobs if j.job_id == "ext-stale-one"), None)
    assert stale is not None
    assert stale.exit_reason == "stale_detected"
```

- [ ] **Step 2: Run tests — confirm failure**

```
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/api/test_snapshot_exit_reason.py -v
```

Expected: first two tests fail with `TypeError: JobSnapshot.__init__() got an unexpected keyword argument 'exit_reason'`. Last two fail because the provider doesn't pass it yet.

- [ ] **Step 3: Add `exit_reason` to `JobSnapshot`**

In `src/quodeq/core/types/job.py`, update the dataclass:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: str
    status: str
    command: str = ""
    started_at: str = ""
    ended_at: str | None = None
    exit_code: int | None = None
    logs: list[str] = field(default_factory=list)
    output_project: str | None = None
    output_run_id: str | None = None
    phase: str | None = None
    current_dimension: str | None = None
    dimensions: list[str] | None = None
    error: str | None = None
    source: str = "internal"  # "internal" | "external"
    exit_reason: str | None = None
```

- [ ] **Step 4: Pass `exit_reason` through in `_run_row_to_snapshot`**

In `src/quodeq/services/filesystem.py`, locate the `_run_row_to_snapshot` method added in Plan B1 (Task 4). It currently ends with something like:

```python
return JobSnapshot(
    job_id=row.job_id,
    status=row.state,
    ...
    error=row.exit_reason,
    source="external" if row.job_id.startswith("ext-") else "internal",
)
```

Add `exit_reason=row.exit_reason,` to the returned `JobSnapshot`. Keep `error=row.exit_reason` as-is (it also mirrors the value for backward compat with any UI code that reads `error`). Final:

```python
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
    exit_reason=row.exit_reason,
)
```

- [ ] **Step 5: Run tests — confirm pass**

```
uv run pytest tests/api/test_snapshot_exit_reason.py -v
uv run pytest -q
```

Expected: 4 new tests PASS, full suite stays green.

- [ ] **Step 6: Commit**

```
git add src/quodeq/core/types/job.py src/quodeq/services/filesystem.py tests/api/test_snapshot_exit_reason.py
git commit -m "feat(snapshot): add exit_reason field and plumb through provider"
```

---

## Task 2: UI — `ExternalRunBadge` rewrite + `StatusChip` extraction + stale CSS

**Files:**
- Modify: `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.jsx`
- Modify: CSS file owning `.job-status-badge` styles (find with `grep -rn 'job-status-badge' src/quodeq/ui/src/styles/`)
- Test: `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.test.jsx` (new)

- [ ] **Step 1: Write failing test**

Create `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import EvaluationStatus from './EvaluationStatus.jsx';

// Mock child components so we isolate what we care about.
vi.mock('./LiveTerminal.jsx', () => ({ default: () => null }));
vi.mock('./LiveViolationsFeed.jsx', () => ({ default: () => null }));

const baseJob = {
  jobId: 'ext-test',
  status: 'done',
  source: 'external',
  logs: [],
  dimensions: [],
};

describe('StatusChip', () => {
  it('renders plain status text for a done run', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'done' }} />);
    const chip = document.querySelector('.job-status-badge');
    expect(chip.textContent).toBe('done');
    expect(chip.className).not.toContain('job-status-badge--stale');
  });

  it('renders "cancelled (stale)" with --stale class when exitReason starts with "stale_"', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'cancelled', exitReason: 'stale_detected' }} />);
    const chip = document.querySelector('.job-status-badge');
    expect(chip.textContent).toBe('cancelled (stale)');
    expect(chip.className).toContain('job-status-badge--stale');
    expect(chip.getAttribute('title')).toBe('stale_detected');
  });

  it('renders plain "cancelled" for user-initiated cancel (signal)', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'cancelled', exitReason: 'signal_SIGTERM' }} />);
    const chip = document.querySelector('.job-status-badge');
    expect(chip.textContent).toBe('cancelled');
    expect(chip.className).not.toContain('job-status-badge--stale');
    expect(chip.getAttribute('title')).toBe('signal_SIGTERM');
  });

  it('renders "failed" with tooltip showing exception reason', () => {
    render(<EvaluationStatus job={{ ...baseJob, status: 'failed', exitReason: 'exception: EvaluationError' }} />);
    const chip = document.querySelector('.job-status-badge');
    expect(chip.textContent).toBe('failed');
    expect(chip.className).not.toContain('job-status-badge--stale');
    expect(chip.getAttribute('title')).toBe('exception: EvaluationError');
  });
});

describe('ExternalRunBadge', () => {
  it('renders "External" when job.source is "external"', () => {
    render(<EvaluationStatus job={{ ...baseJob, source: 'external' }} />);
    expect(screen.getByText('External')).toBeInTheDocument();
  });

  it('renders nothing for source="internal"', () => {
    render(<EvaluationStatus job={{ ...baseJob, source: 'internal' }} />);
    expect(screen.queryByText('External')).toBeNull();
    expect(screen.queryByText('Running outside the dashboard')).toBeNull();
  });
});
```

(If `vi.mock` isn't available because vitest isn't imported, import it at the top:
```jsx
import { vi } from 'vitest';
```
)

- [ ] **Step 2: Run test — confirm failure**

```
cd src/quodeq/ui
npx vitest run src/features/evaluation/components/EvaluationStatus.test.jsx
```

Expected: FAIL — text is still "Running outside the dashboard"; chip text is raw status; no `--stale` class.

- [ ] **Step 3: Rewrite `ExternalRunBadge` + add `StatusChip`**

In `src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.jsx`:

Replace the existing `ExternalRunBadge` (lines ~52-59):

```jsx
function ExternalRunBadge() {
  return (
    <div className="job-meta-item">
      <span className="job-meta-label">Source</span>
      <span className="job-meta-value">External</span>
    </div>
  );
}
```

Add a new `StatusChip` component above `JobHeader` (insert around line 110):

```jsx
function StatusChip({ status, exitReason }) {
  const isStale = status === 'cancelled' && typeof exitReason === 'string' && exitReason.startsWith('stale_');
  const text = isStale ? 'cancelled (stale)' : status;
  const className = `job-status-badge ${status}${isStale ? ' job-status-badge--stale' : ''}`;
  return (
    <span className={className} title={exitReason ?? ''}>
      {text}
    </span>
  );
}
```

In `JobHeader` (around line 122), replace:

```jsx
<span className={`job-status-badge ${job.status}`}>{job.status}</span>
```

with:

```jsx
<StatusChip status={job.status} exitReason={job.exitReason} />
```

- [ ] **Step 4: Add the `--stale` CSS rule**

Find the stylesheet that defines `.job-status-badge`:

```
grep -rn '\.job-status-badge' src/quodeq/ui/src/
```

In the file(s) where existing badge styles live, append a `--stale` variant. Use existing theme variables where possible. Conservative fallback:

```css
.job-status-badge--stale {
  background: var(--color-warning-bg, #422c0a);
  color: var(--color-warning-fg, #ffc864);
  border-color: var(--color-warning-border, #6a4c0f);
}
```

If the file uses a different variable naming convention (e.g., `--chip-stale-bg` or `--amber-*`), match it. The goal: amber color, visually distinct from the gray/red of plain cancelled/failed chips.

- [ ] **Step 5: Run — confirm pass**

```
cd src/quodeq/ui
npx vitest run src/features/evaluation/components/EvaluationStatus.test.jsx
npm run build
```

Expected: all 6 UI tests PASS; `npm run build` exits 0.

- [ ] **Step 6: Commit**

```
git add src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.jsx
git add src/quodeq/ui/src/features/evaluation/components/EvaluationStatus.test.jsx
# Plus whatever CSS file you modified:
git add src/quodeq/ui/src/styles/<path>.css
git commit -m "feat(ui): StatusChip + concise External badge + stale amber styling"
```

---

## Task 3: Delete dead code

**Files:**
- Modify: `src/quodeq/services/_external_jobs.py` (delete dead helpers, keep cancel path)
- Modify: `src/quodeq/services/jobs.py` (delete `_get_external`, simplify `get_job` / `list_jobs`)
- Modify: `tests/services/test_external_jobs.py` (delete tests for removed functions)

- [ ] **Step 1: Audit surviving dependencies**

Before deleting, confirm nothing else imports the functions we're removing:

```
grep -rn 'find_external_runs\|_run_dir_to_snapshot\|_infer_progress\|_get_external\|_pid_liveness\|_manifest_started_at' src/quodeq/ tests/
```

Expected call sites (ALL internal to the files we're editing):
- `src/quodeq/services/_external_jobs.py` — the defining file.
- `src/quodeq/services/jobs.py` lines 187, 194-204, 227-228 — we're removing all of these.
- `tests/services/test_external_jobs.py` — tests for the removed functions (to be deleted).

If anything else imports these, STOP and flag — we may have missed a production dependency.

- [ ] **Step 2: Update `_external_jobs.py`**

Rewrite `src/quodeq/services/_external_jobs.py` to this final form (keeping only the cancel-flow helpers):

```python
"""SIGTERM cancel path for external (CLI-started) evaluations.

Dashboard-side detection and status inference for external runs now
lives in ``services/run_index.py`` and ``services/_index_sync.py`` (Plan B1).
Only the cancel path — reading the ``.pid`` file and delivering SIGTERM —
remains here.
"""
from __future__ import annotations

import logging
import os
import signal
from pathlib import Path

_logger = logging.getLogger(__name__)

_PID_FILENAME = ".pid"


def resolve_external_pid(project_uuid: str, run_id: str, reports_root: Path) -> int | None:
    """Find the PID of the process running an external job, for cancellation.

    Looks for a `.pid` file written by `quodeq evaluate` at run start. Returns
    None if not found or the process is already gone.
    """
    pid_file = reports_root / project_uuid / run_id / _PID_FILENAME
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def cancel_external_run(project_uuid: str, run_id: str, reports_root: Path) -> bool:
    """Send SIGTERM to the external run's process. Returns True if signal sent."""
    pid = resolve_external_pid(project_uuid, run_id, reports_root)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError as exc:
        _logger.warning("Failed to signal pid %s: %s", pid, exc)
        return False
```

Removed: `find_external_runs`, `_run_dir_to_snapshot`, `_infer_progress`, `_pid_liveness`, `_is_pid_alive`, `_manifest_started_at`, and the now-unused imports (`json`, `replace`, `datetime`, `timezone`, `JobSnapshot`, `_EXTERNAL_JOB_ID_PREFIX`, `_MANIFEST_PATH`, `_SCAN_FILENAME`).

- [ ] **Step 3: Simplify `jobs.py`**

In `src/quodeq/services/jobs.py`:

Replace `get_job` (around line 180-192) with:

```python
def get_job(self, job_id: str, reports_root: Path | None = None) -> JobSnapshot | None:
    """Return the current state of an in-memory job, or None if not found.

    External runs (``ext-`` prefix) are not tracked in-memory — they are
    served by ``FilesystemActionProvider.get_evaluation_status`` via the
    SQLite index. Callers that encounter an ``ext-`` id here should route
    through the provider instead.
    """
    if job_id.startswith("ext-"):
        return None
    with self._lock:
        job = self._store.get(job_id)
        if not job:
            return None
        return job.to_dict()
```

Delete `_get_external` entirely (lines 194-204).

Replace the `find_external_runs` branch in `list_jobs` (around lines 226-228 and the downstream merge block). Find the full `list_jobs` body; the simplified version returns only internal jobs:

```python
def list_jobs(
    self,
    *,
    limit: int = _DEFAULT_LIST_LIMIT,
    offset: int = 0,
    reports_root: Path | None = None,
) -> list[JobSnapshot]:
    """Return tracked in-memory jobs as frozen snapshots with pagination.

    External runs are served via the SQLite index, not JobManager. The
    ``reports_root`` kwarg is retained for signature compatibility with
    callers that still pass it; it is ignored here.
    """
    _ = reports_root  # intentional: retained for compat, not used
    with self._lock:
        internal = [job.to_dict() for job in self._store.list()]
    # Preserve existing ordering (newest first).
    internal.sort(key=lambda s: s.started_at or "", reverse=True)
    if limit == 0:
        return internal[offset:]
    return internal[offset:offset + limit]
```

Remove any now-unused imports at the top of `jobs.py` (`find_external_runs` was likely imported lazily inside the function, so there's nothing to remove at module level; verify with grep).

- [ ] **Step 4: Delete/simplify `test_external_jobs.py`**

First inspect the file:

```
wc -l tests/services/test_external_jobs.py
grep -n 'def test_\|from quodeq' tests/services/test_external_jobs.py
```

Delete every test that references `find_external_runs`, `_run_dir_to_snapshot`, or `_infer_progress` (by function name or via `from quodeq.services._external_jobs import ...`). Keep tests that exercise `resolve_external_pid` or `cancel_external_run`.

If after deletion the file has no remaining tests, delete the file entirely:

```
rm tests/services/test_external_jobs.py
```

If it retains tests for the cancel path, make sure the imports at the top only reference the two surviving functions.

- [ ] **Step 5: Run full suite — confirm green**

```
uv run pytest -q
```

Expected: full suite green (Plan B1's `test_index_e2e.py`, `test_index_backed_provider.py`, `test_run_index.py`, `test_index_sync.py` all still pass — they already exercise the real provider chain that replaces this dead code).

If any test fails due to the deletion, STOP. Investigate — either the test was testing the old heuristic directly (expected to fail, delete it) OR we accidentally broke a still-live path (unexpected, fix).

- [ ] **Step 6: Commit**

```
git add src/quodeq/services/_external_jobs.py src/quodeq/services/jobs.py
# Plus whatever happened to the test file:
git add tests/services/test_external_jobs.py  # (or git rm if deleted)
git commit -m "chore: delete dead external-run detection code (Plan B1 replaced it)"
```

---

## Post-Implementation Verification

Manual smoke checks after all three tasks:

1. Start the dashboard (`quodeq dashboard --dev --browser`).
2. Run a CLI evaluation in another terminal. Let it complete.
   - ✅ Dashboard lists the run with "External" badge (short, not "Running outside the dashboard").
   - ✅ Chip shows green `done`.
3. Run a CLI evaluation; kill with `kill -9` mid-run. Wait 30s for heartbeat staleness, refresh dashboard.
   - ✅ Chip shows amber `cancelled (stale)`, tooltip on hover reads `stale_detected`.
4. Run a dashboard-initiated evaluation (from the UI).
   - ✅ NO "External" badge.
   - ✅ Chip reflects live state.
5. Cancel it with Ctrl+C equivalent from the dashboard.
   - ✅ Chip shows gray `cancelled` (not amber), tooltip reads `signal_SIGTERM` or similar.

## Rollback

Each task is a standalone commit. All three are additive UI/plumbing changes except Task 3 (deletion) — and Task 3 only removes code that is already unreachable after Plan B1. Reverting any single commit is safe.

## Out of Scope

- "Rebuild Index" button — deferred as noted in the spec.
- Fine-grained cancel categorization (user/signal/atexit differentiation in chip text).
- Polish items from prior PR reviews (live-terminal I2/I3, Task 1 race) — separate follow-up.
