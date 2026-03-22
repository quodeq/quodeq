# Token Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce token consumption by 80-95% through adaptive agent scaling and multi-dimension consolidation.

**Architecture:** Phase 1 changes SubagentPool to scout-then-scale (start 1 agent, scale up based on queue depth), adds adaptive files-per-agent tiers, and exposes `maxSubagents` to the web UI. Phase 2 adds a consolidated prompt template that evaluates all dimensions in one pass, requiring MCP server and evidence parser changes for multi-dimension support.

**Tech Stack:** Python (backend), React (web UI), pytest (tests)

**Spec:** `docs/superpowers/specs/2026-03-22-token-optimization-design.md`

**Test command:** `pytest tests/ -v` (from repo root)

**Important:** Never add co-author lines to commits.

---

## Phase 1: Adaptive Agent Scaling

### Task 1: `_compute_files_per_agent` function

**Files:**
- Modify: `src/quodeq/analysis/subagents/runner.py:23-27`
- Test: `tests/engine/test_subagent_runner.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/engine/test_subagent_runner.py`:

```python
"""Tests for adaptive subagent runner functions."""
from __future__ import annotations

from quodeq.analysis.subagents.runner import _compute_files_per_agent  # direct import (no re-export)


class TestComputeFilesPerAgent:
    def test_small_project_no_rotation(self):
        assert _compute_files_per_agent(20) == 20

    def test_boundary_50(self):
        assert _compute_files_per_agent(50) == 50

    def test_medium_project(self):
        assert _compute_files_per_agent(100) == 50

    def test_boundary_200(self):
        assert _compute_files_per_agent(200) == 50

    def test_large_project(self):
        assert _compute_files_per_agent(500) == 75

    def test_boundary_1000(self):
        assert _compute_files_per_agent(1000) == 75

    def test_very_large_project(self):
        assert _compute_files_per_agent(5000) == 100

    def test_minimum_1(self):
        assert _compute_files_per_agent(1) == 1

    def test_zero_files(self):
        assert _compute_files_per_agent(0) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/engine/test_subagent_runner.py -v`
Expected: ImportError — `_compute_files_per_agent` does not exist yet.

- [ ] **Step 3: Implement `_compute_files_per_agent`**

In `src/quodeq/analysis/subagents/runner.py`, add after the existing constants (line 27):

```python
def _compute_files_per_agent(total_files: int) -> int:
    """Compute adaptive max files per agent based on project size.

    Larger projects get higher limits to reduce context rotation overhead
    (each rotation spawns a new CLI session with ~8K tokens of fixed cost).
    """
    if total_files <= 0:
        return 0
    if total_files <= 50:
        return total_files
    if total_files <= 200:
        return 50
    if total_files <= 1000:
        return 75
    return 100
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/engine/test_subagent_runner.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 5: Wire `_compute_files_per_agent` into `process_dimension_with_subagents`**

In `src/quodeq/analysis/subagents/runner.py`, modify `process_dimension_with_subagents` around line 212. Change:

```python
FileQueue(queue_path, files, max_files_per_agent=_MAX_FILES_PER_AGENT)
```

To:

```python
files_per_agent = _compute_files_per_agent(len(files))
FileQueue(queue_path, files, max_files_per_agent=files_per_agent)
```

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/analysis/subagents/runner.py tests/engine/test_subagent_runner.py
git commit -m "feat: adaptive files-per-agent based on project size"
```

---

### Task 2: Scout-then-scale pool strategy

**Files:**
- Modify: `src/quodeq/analysis/subprocess.py:41-54` (add `max_files_per_agent` field)
- Modify: `src/quodeq/analysis/subagents/pool.py:66-87, 241-256`
- Test: `tests/engine/test_subagent_pool.py`

- [ ] **Step 1: Add `max_files_per_agent` to `AnalysisConfig`**

In `src/quodeq/analysis/subprocess.py`, add to the `AnalysisConfig` frozen dataclass (after `agent_id` field, line 54):

```python
max_files_per_agent: int = 30
```

Note: `AnalysisConfig` is `@dataclass(frozen=True)` — fields are set at construction only.

- [ ] **Step 2: Wire `max_files_per_agent` from runner into `AnalysisConfig`**

In `src/quodeq/analysis/subagents/runner.py`, update `_launch_pool` (line 83-96) to pass `max_files_per_agent` when constructing `AnalysisConfig`:

```python
files_per_agent = _compute_files_per_agent(len(files))  # from Task 1
base_ac = AnalysisConfig(
    ...existing fields...,
    max_files_per_agent=files_per_agent,
)
```

Also update the `FileQueue` creation (already done in Task 1) to use the same value.

- [ ] **Step 3: Write the failing test for `_compute_scale_up`**

Add to `tests/engine/test_subagent_pool.py`:

```python
from math import ceil

class TestComputeScaleUp:
    def _make_pool(self, n_agents, tmp_path, max_files=30):
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["f.py"])
        return SubagentPool(
            n_agents=n_agents,
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            prompt="test",
            dimension="security",
            config=AnalysisConfig(max_files_per_agent=max_files),
        )

    def test_no_remaining_returns_zero(self, tmp_path):
        pool = self._make_pool(5, tmp_path)
        assert pool._compute_scale_up(0) == 0

    def test_remaining_within_one_batch(self, tmp_path):
        pool = self._make_pool(5, tmp_path)
        # 25 remaining, fits in 1 agent batch (30 default) → 0 extra agents
        assert pool._compute_scale_up(25) == 0

    def test_remaining_needs_two_agents(self, tmp_path):
        pool = self._make_pool(5, tmp_path)
        # 50 remaining → ceil(50/30) = 2 → min(2, 5-1) = 2 extra
        assert pool._compute_scale_up(50) == 2

    def test_remaining_capped_by_max_agents(self, tmp_path):
        pool = self._make_pool(3, tmp_path)
        # 200 remaining → ceil(200/30) = 7 → min(7, 3-1) = 2 extra
        assert pool._compute_scale_up(200) == 2

    def test_max_agents_1_never_scales(self, tmp_path):
        pool = self._make_pool(1, tmp_path)
        assert pool._compute_scale_up(500) == 0
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/engine/test_subagent_pool.py::TestComputeScaleUp -v`
Expected: AttributeError — `_compute_scale_up` does not exist on SubagentPool.

- [ ] **Step 5: Implement `_compute_scale_up` method**

In `src/quodeq/analysis/subagents/pool.py`, add import at top:

```python
from math import ceil
```

Add method to `SubagentPool` class (after `__init__`):

```python
def _compute_scale_up(self, remaining: int) -> int:
    """Compute how many overflow agents to spawn after scout completes."""
    if remaining <= 0:
        return 0
    batch = self._base_config.max_files_per_agent or 30
    needed = ceil(remaining / batch)
    if needed <= 1:
        return 0
    return min(needed, self._n - 1)
```

- [ ] **Step 6: Run `_compute_scale_up` tests**

Run: `pytest tests/engine/test_subagent_pool.py::TestComputeScaleUp -v`
Expected: All 5 tests PASS.

- [ ] **Step 7: Write the failing test for scout-then-scale behavior**

Add to `tests/engine/test_subagent_pool.py`:

```python
class TestScoutThenScale:
    def test_small_queue_uses_one_agent(self, tmp_path):
        """20 files with max_agents=5 → only 1 agent should run (scout handles all)."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(20)])

        pool = SubagentPool(
            n_agents=5,
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            prompt="analyse",
            dimension="security",
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents.pool.run_analysis", _fake_run_analysis):
            results = pool.run()

        # Only 1 agent should have been spawned for 20 files
        assert len(results) == 1
        assert results[0].agent_id == "agent-0"

    def test_large_queue_scales_up(self, tmp_path):
        """200 files with max_agents=5 → scout + overflow agents."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(200)], max_files_per_agent=30)

        pool = SubagentPool(
            n_agents=5,
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            prompt="analyse",
            dimension="security",
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents.pool.run_analysis", _fake_run_analysis):
            results = pool.run()

        # Multiple agents should have been spawned
        assert len(results) > 1
        # But first agent should always be agent-0 (the scout)
        assert results[0].agent_id == "agent-0"
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `pytest tests/engine/test_subagent_pool.py::TestScoutThenScale -v`
Expected: FAIL — `test_small_queue_uses_one_agent` fails because pool still launches all 5 agents at once.

- [ ] **Step 9: Implement scout-then-scale in `_run_pool_loop`**

Replace `SubagentPool._run_pool_loop` in `src/quodeq/analysis/subagents/pool.py`:

```python
_SCOUT_TIMEOUT_S = 180  # 3 minutes before forcing scale-up

def _run_pool_loop(
    self, results: list[SubagentResult], max_duration: float, pool_start: float,
) -> None:
    """Execute scout-then-scale pool loop.

    1. Launch 1 scout agent
    2. When scout completes (or timeout), check queue and scale up if needed
    3. Continue with respawn-on-completion for remaining work
    """
    scout_timeout = min(
        _SCOUT_TIMEOUT_S,
        max_duration / max(self._n, 1) * 0.5,
    )
    scout_done = False

    with ThreadPoolExecutor(max_workers=self._n) as pool:
        # Phase 1: Launch scout
        self._finished[f"{_AGENT_ID_PREFIX}-{self._next_idx}"] = False
        self._futures[pool.submit(self._run_single, self._next_idx)] = self._next_idx
        self._next_idx += 1

        while self._futures:
            done = self._collect_done(results)

            # Phase 2: Scale up after scout completes or times out
            if not scout_done:
                elapsed = time.monotonic() - pool_start
                scout_completed = len(done) > 0
                scout_timed_out = elapsed >= scout_timeout and self._n > 1

                if scout_completed or scout_timed_out:
                    scout_done = True
                    remaining = self._should_respawn(pool_start, max_duration)
                    overflow = self._compute_scale_up(remaining)
                    for _ in range(overflow):
                        self._finished[f"{_AGENT_ID_PREFIX}-{self._next_idx}"] = False
                        self._futures[pool.submit(self._run_single, self._next_idx)] = self._next_idx
                        self._next_idx += 1

            if not done:
                time.sleep(_FUTURE_POLL_INTERVAL_S)
                continue

            # Phase 3: Normal respawn-on-completion
            if scout_done:
                self._process_completed_futures(done, pool_start, max_duration, pool)
```

Also update `run()` to log the new behavior:

```python
log_info(f"Launching scout agent for {self._dimension} (max {self._n} agents)")
```

- [ ] **Step 10: Run scout-then-scale tests**

Run: `pytest tests/engine/test_subagent_pool.py::TestScoutThenScale -v`
Expected: Both tests PASS.

- [ ] **Step 11: Run existing pool tests to verify no regressions**

Run: `pytest tests/engine/test_subagent_pool.py -v`
Expected: All tests pass. Note: existing `test_launches_n_agents` may need updating since it expects exactly 3 agents for 20 files — with scout-then-scale, only 1 agent runs for 20 files.

If it fails, update `test_launches_n_agents` to use 200 files (enough to trigger scale-up):

```python
def test_launches_n_agents(self, tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    FileQueue(queue_path, [f"src/f{i}.py" for i in range(200)], max_files_per_agent=30)

    pool = SubagentPool(
        n_agents=3,
        paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
        prompt="analyse files",
        dimension="maintainability",
        config=AnalysisConfig(max_files_per_agent=30),
    )

    with patch("quodeq.analysis.subagents.pool.run_analysis", _fake_run_analysis):
        results = pool.run()

    assert len(results) >= 2  # scout + at least 1 overflow
    assert all(r.success for r in results)
```

- [ ] **Step 12: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 13: Commit**

```bash
git add src/quodeq/analysis/subagents/pool.py src/quodeq/analysis/subprocess.py src/quodeq/analysis/subagents/runner.py tests/engine/test_subagent_pool.py
git commit -m "feat: scout-then-scale pool strategy for adaptive agent count"
```

---

### Task 3: Rename `n_subagents` to `max_subagents`

**Files:**
- Modify: `src/quodeq/analysis/runner.py:42`
- Modify: `src/quodeq/analysis/subagents/runner.py:91, 213`
- Modify: `src/quodeq/cli.py:181`
- Modify: `src/quodeq/cli_parser.py:8, 46-47`

- [ ] **Step 1: Rename `AnalysisOptions.n_subagents` to `max_subagents`**

In `src/quodeq/analysis/runner.py:42`, change:

```python
n_subagents: int = 1
```

To:

```python
max_subagents: int = 1
```

- [ ] **Step 2: Update all references to `n_subagents` in runner.py**

In `src/quodeq/analysis/runner.py:237`, change:

```python
if config.options.n_subagents > 1:
```

To:

```python
if config.options.max_subagents > 1:
```

- [ ] **Step 3: Update subagents/runner.py references**

In `src/quodeq/analysis/subagents/runner.py:91`, change:

```python
n_agents=config.options.n_subagents,
```

To:

```python
n_agents=config.options.max_subagents,
```

In line 213, change:

```python
log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {len(files)} files queued for {config.options.n_subagents} subagents")
```

To:

```python
log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {len(files)} files queued (max {config.options.max_subagents} agents)")
```

- [ ] **Step 4: Update CLI to use new field name**

In `src/quodeq/cli.py:181`, change:

```python
n_subagents=args.n_subagents,
```

To:

```python
max_subagents=args.n_subagents,
```

- [ ] **Step 5: Add `--max-subagents` alias in cli_parser.py**

In `src/quodeq/cli_parser.py:45-48`, change:

```python
parser.add_argument(
    "--n-subagents", type=int, default=_DEFAULT_N_SUBAGENTS,
    help="Number of parallel subagents per dimension (default: %(default)s)",
)
```

To:

```python
parser.add_argument(
    "--n-subagents", "--max-subagents", type=int, default=_DEFAULT_N_SUBAGENTS,
    dest="n_subagents",
    help="Max parallel subagents per dimension (default: %(default)s)",
)
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass. If any test references `n_subagents` on `AnalysisOptions`, update it.

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/analysis/runner.py src/quodeq/analysis/subagents/runner.py src/quodeq/cli.py src/quodeq/cli_parser.py
git commit -m "refactor: rename n_subagents to max_subagents (now a ceiling, not fixed count)"
```

---

### Task 4: Expose `maxSubagents` in web API and UI

**Files:**
- Modify: `src/quodeq/services/base.py:12-20`
- Modify: `src/quodeq/services/evaluation_mixin.py:55-72`
- Modify: `src/quodeq/api/routes.py:189-198`
- Modify: `src/quodeq/ui/src/api/index.js` (verify exact path during implementation)
- Modify: `src/quodeq/ui/src/features/evaluation/components/EvaluationForm.jsx` (verify exact path — check `App.jsx` and `EvaluateScreen.jsx` for where evaluation params are assembled)
- Test: `tests/test_api_routes.py` (if exists, add test)

- [ ] **Step 1: Add `max_subagents` to `EvaluationOptions`**

In `src/quodeq/services/base.py`, add to the dataclass:

```python
@dataclass
class EvaluationOptions:
    """Options controlling an evaluation run."""
    discipline: str | None = None
    dimensions: str = ""
    numerical: bool = False
    ai_cmd: str | None = None
    ai_model: str | None = None
    subagent_model: str | None = None
    verify_findings: bool = True
    max_subagents: int = 5
```

- [ ] **Step 2: Pass `--n-subagents` in `_build_evaluate_cmd`**

In `src/quodeq/services/evaluation_mixin.py`, modify `_build_evaluate_cmd` (around line 63-72). After the numerical flag, add:

```python
if options.max_subagents != 5:
    cmd += ["--n-subagents", str(options.max_subagents)]
```

- [ ] **Step 3: Accept `maxSubagents` in API route**

In `src/quodeq/api/routes.py`, around line 189-198, add to the EvaluationOptions construction:

```python
max_subagents_raw = payload.get("maxSubagents", 5)
max_subagents = max(1, min(10, int(max_subagents_raw)))
```

And pass it:

```python
options=EvaluationOptions(
    discipline=payload.get("discipline"),
    dimensions=payload.get("dimensions") or "",
    numerical=bool(payload.get("numerical")),
    ai_cmd=ai_cmd,
    ai_model=payload.get("aiModel") or None,
    subagent_model=payload.get("subagentModel") or None,
    verify_findings=bool(payload.get("verifyFindings", False)),
    max_subagents=max_subagents,
),
```

- [ ] **Step 4: Add `maxSubagents` to the web UI API call**

In `src/quodeq/ui/src/api/index.js`, find the `startEvaluation` function and ensure the payload includes `maxSubagents` when provided.

In `src/quodeq/ui/src/features/evaluation/components/EvaluationForm.jsx` (or parent `EvaluateScreen.jsx` / `App.jsx` depending on where settings are collected):

Add a number input for "Max parallel agents":

```jsx
<label>
  Max parallel agents
  <input
    type="number"
    min={1}
    max={10}
    value={maxSubagents}
    onChange={(e) => setMaxSubagents(Number(e.target.value))}
  />
</label>
```

Pass `maxSubagents` in the API call payload alongside existing parameters.

Note: Follow the existing React component patterns in the codebase. Check `EvaluateScreen.jsx` and `SettingsPage.jsx` for how other settings (like `verifyFindings`, `aiModel`) are wired. Mirror that pattern.

- [ ] **Step 5: Run backend tests**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/services/base.py src/quodeq/services/evaluation_mixin.py src/quodeq/api/routes.py src/quodeq/ui/
git commit -m "feat: expose maxSubagents setting in web API and UI"
```

---

### Task 5: Phase 1 integration test

**Files:**
- Test: `tests/engine/test_adaptive_scaling_integration.py` (create)

- [ ] **Step 1: Write integration test verifying end-to-end adaptive behavior**

Create `tests/engine/test_adaptive_scaling_integration.py`:

```python
"""Integration test: adaptive scaling reduces agent count for small projects."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.engine.file_queue import FileQueue
from quodeq.engine.subagent_pool import PoolPaths, SubagentPool


def _counting_run_analysis(call_log):
    """Factory: returns a mock run_analysis that logs agent IDs."""
    def _inner(work_dir, prompt, stream_file, config):
        stream_file.parent.mkdir(parents=True, exist_ok=True)
        stream_file.write_text("")
        call_log.append(config.agent_id)
        if config.queue_path:
            from quodeq.engine.file_queue import FileQueue
            queue = FileQueue(config.queue_path)
            queue.take(queue.remaining(), agent_id=config.agent_id)
        if config.jsonl_file:
            with open(config.jsonl_file, "a") as f:
                f.write(json.dumps({
                    "schema_version": 1, "p": "Test", "t": "compliance",
                    "d": "security", "w": "ok", "file": "a.py", "line": 1,
                }) + "\n")
    return _inner


class TestAdaptiveScalingIntegration:
    def test_20_files_uses_1_agent(self, tmp_path):
        """The exact scenario from the spec: 20 files should use 1 agent."""
        call_log = []
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(20)])

        pool = SubagentPool(
            n_agents=5,
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            prompt="analyse",
            dimension="security",
        )

        with patch("quodeq.analysis.subagents.pool.run_analysis",
                    _counting_run_analysis(call_log)):
            results = pool.run()

        assert len(call_log) == 1, f"Expected 1 agent, got {len(call_log)}: {call_log}"
        assert call_log[0] == "agent-0"

    def test_200_files_scales_up(self, tmp_path):
        """200 files should trigger scale-up beyond scout."""
        call_log = []
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(200)], max_files_per_agent=30)

        pool = SubagentPool(
            n_agents=5,
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            prompt="analyse",
            dimension="security",
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents.pool.run_analysis",
                    _counting_run_analysis(call_log)):
            results = pool.run()

        assert len(call_log) > 1, f"Expected multiple agents, got {len(call_log)}"
        assert call_log[0] == "agent-0"  # scout always first
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/engine/test_adaptive_scaling_integration.py -v`
Expected: Both tests PASS.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/engine/test_adaptive_scaling_integration.py
git commit -m "test: integration tests for adaptive agent scaling"
```

---

## Phase 2: Multi-Dimension Consolidation

### Task 6: Multi-dimension MCP server args and refs loading

**Files:**
- Modify: `src/quodeq/analysis/mcp/args.py`
- Modify: `src/quodeq/core/standards/refs.py`
- Test: `tests/engine/test_mcp_args.py` (create or extend)
- Test: `tests/core/test_refs_multi.py` (create or extend)

- [ ] **Step 1: Read current `args.py` and `refs.py` to understand the interface**

Read: `src/quodeq/analysis/mcp/args.py` and `src/quodeq/core/standards/refs.py`

- [ ] **Step 2: Write failing test for comma-separated `--dimension` parsing**

Test that `parse_args(["server.py", "output.jsonl", "--dimension", "security,maintainability"])` returns a `ServerArgs` with `dimensions=["security", "maintainability"]`.

- [ ] **Step 3: Implement comma-separated dimension parsing in args.py**

Change the `--dimension` argument to split on commas. The `ServerArgs` dataclass gets a `dimensions: list[str]` field (keep `dimension: str | None` for backward compat as a property returning the first element).

- [ ] **Step 4: Write failing test for multi-dimension refs loading**

Test that `load_compiled_requirements(compiled_dir, "security,maintainability")` or a new `load_compiled_requirements_multi(compiled_dir, ["security", "maintainability"])` returns requirements from both dimensions.

- [ ] **Step 5: Implement multi-dimension refs loading**

Add `load_compiled_requirements_multi(compiled_dir, dimensions)` and `load_compiled_refs_multi(compiled_dir, dimensions)` that iterate dimensions, load each, and merge.

- [ ] **Step 6: Run tests**

Run: `pytest tests/ -v -k "mcp_args or refs_multi"`
Expected: All new tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/analysis/mcp/args.py src/quodeq/core/standards/refs.py tests/
git commit -m "feat: multi-dimension support in MCP args and standards refs"
```

---

### Task 7: Multi-dimension FindingsRouter

**Files:**
- Modify: `src/quodeq/analysis/mcp/findings_server.py`
- Test: existing findings server tests (extend)

- [ ] **Step 1: Read `FindingsRouter.__init__` and `_enrich` to understand current single-dimension logic**

Read: `src/quodeq/analysis/mcp/findings_server.py:39-90`

- [ ] **Step 2: Write failing test for req-ID-to-dimension derivation**

Test that when `FindingsRouter` is initialized with `dimensions=["security", "maintainability"]` and receives a finding with `req="S-CON-1"`, the enriched finding has `d="security"`. Similarly, `req="M-MOD-1"` → `d="maintainability"`.

- [ ] **Step 3: Implement multi-dimension FindingsRouter**

Modify `FindingsRouter.__init__` to:
1. Accept `dimensions: list[str] | None` alongside the existing `dimension: str | None` (backward compat)
2. When multiple dimensions: load compiled requirements for ALL dimensions, build a `req_prefix → dimension` mapping at init time
3. In `_enrich()`: derive `d` from the req ID using the mapping instead of `self._dimension`

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v -k "findings"`
Expected: All tests pass (old single-dimension + new multi-dimension).

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/mcp/findings_server.py tests/
git commit -m "feat: FindingsRouter derives dimension from req ID for consolidated mode"
```

---

### Task 8: Multi-dimension AnalysisConfig and subprocess

**Files:**
- Modify: `src/quodeq/analysis/subprocess.py:41-54, 57-89`
- Modify: `src/quodeq/analysis/subagents/pool.py:66-118`

- [ ] **Step 1: Update AnalysisConfig for multi-dimension**

In `src/quodeq/analysis/subprocess.py`, change `dimension: str | None = None` to accept comma-separated dimensions. Keep backward compat — a single dimension string still works.

- [ ] **Step 2: Update `_create_mcp_config` to pass comma-separated dimensions**

Modify the `--dimension` arg passed to the MCP server to use the comma-separated value when multiple dimensions are provided.

- [ ] **Step 3: Update SubagentPool to accept `dimensions: list[str]`**

In `src/quodeq/analysis/subagents/pool.py`:
- `__init__`: Accept `dimension: str | list[str]`. Store as `self._dimensions: list[str]` and `self._dimension_key: str` (comma-joined for file naming, or `"consolidated"`).
- `_shared_jsonl_path`: Use `self._dimension_key` instead of `self._dimension`.
- `_build_agent_config`: Pass comma-separated dimensions to `AnalysisConfig`.
- Keep backward compat: single string dimension still works as before.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (existing single-dimension behavior unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/subprocess.py src/quodeq/analysis/subagents/pool.py
git commit -m "feat: multi-dimension support in AnalysisConfig and SubagentPool"
```

---

### Task 9: Consolidated prompt template and builder

**Files:**
- Create: `src/quodeq/data/prompts/consolidated.md`
- Modify: `src/quodeq/analysis/prompts/builder.py`
- Test: `tests/engine/test_prompt_builder.py`

- [ ] **Step 1: Write failing test for `build_consolidated_prompt`**

Add to `tests/engine/test_prompt_builder.py`:

```python
from quodeq.analysis.prompts.builder import build_consolidated_prompt

class TestBuildConsolidatedPrompt:
    def test_includes_all_dimension_standards(self, tmp_path):
        # Create compiled standards for 2 dimensions
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        for dim, req_id in [("security", "S-CON-1"), ("maintainability", "M-MOD-1")]:
            data = {"id": dim, "principles": [{"name": "Test", "source": "iso25010",
                    "requirements": [{"id": req_id, "source": "iso25010",
                    "text": f"Test req for {dim}", "refs": []}]}]}
            (compiled / f"{dim}.json").write_text(json.dumps(data))

        prompt = build_consolidated_prompt(
            dimensions=["security", "maintainability"],
            context=PromptContext(
                language="python", repo_name="test", date_str="2026-03-22",
                dimension="consolidated",  # not used in consolidated mode
                source_file_count=20,
                dimensions_data=_sample_dimensions(),
                standards_dir=tmp_path,
            ),
        )

        assert "S-CON-1" in prompt
        assert "M-MOD-1" in prompt
        assert "security" in prompt.lower()
        assert "maintainability" in prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/engine/test_prompt_builder.py::TestBuildConsolidatedPrompt -v`
Expected: ImportError — `build_consolidated_prompt` doesn't exist.

- [ ] **Step 3: Create `consolidated.md` template**

Create `src/quodeq/data/prompts/consolidated.md`:

```markdown
# {{DISCIPLINE}} Codebase Analysis — Quodeq (Multi-Dimension)

You are a code quality analyst evaluating **{{REPO_NAME}}** across these dimensions: **{{DIMENSION_LIST}}**

{{SOURCE_MANIFEST}}

**Date:** {{DATE}}

---

## Workflow

1. Call `get_next_files()` to receive your next batch of files
2. Read each file using the Read tool
3. Evaluate against ALL dimension checklists below
4. Call `report_finding()` for every violation and compliance you confirm
5. Repeat from step 1 until `get_next_files` returns no more files

**IMPORTANT:** When `get_next_files` returns "DONE" or "no more files", stop immediately.

## report_finding parameters

**Required:** `req` (the **bold requirement ID**, e.g. `M-MOD-1`, `S-CON-3` — server auto-fills principle name and dimension), `t` (`violation` or `compliance`), `file`, `line`, `snippet` (under 200 chars), `severity` (`critical`/`major`/`minor`), `w` (short description)

**Optional:** `reason` (why this is a violation or compliance)

## Rules

- Call `report_finding` immediately after confirming each finding — do not batch
- If it says "Duplicate", move on — already captured
- **Report BOTH violations AND compliance** — scoring uses the ratio
- Every finding must have a specific file, line, and snippet
- Do not fabricate findings — only report what you can see in the code
- Skip generated, vendored, and dependency directories

## Severity

For violations:
- **critical** — Security vulnerability, data loss risk, or crash in production path
- **major** — Significant quality issue that should be fixed
- **minor** — Style issue, minor inefficiency, or improvement opportunity

For compliance — use the same scale for importance of what's done right.

## Standards Checklists

Evaluate each file against ALL dimensions below. The req ID prefix identifies the dimension.

{{STANDARDS_CHECKLISTS}}
```

- [ ] **Step 4: Implement `build_consolidated_prompt` in builder.py**

Add to `src/quodeq/analysis/prompts/builder.py`:

```python
_TPL_DIMENSION_LIST = "DIMENSION_LIST"
_TPL_STANDARDS_CHECKLISTS = "STANDARDS_CHECKLISTS"


def _render_all_standards(standards_dir: Path, dimensions: list[str], work_dir: Path | None) -> str:
    """Render compact standards for all dimensions, separated by headers."""
    compiled_dir = standards_dir / "compiled"
    if not compiled_dir.exists():
        return _NO_STANDARDS
    sections = []
    for dim in dimensions:
        compact = render_compact_standards(compiled_dir, dim)
        if compact != _NO_STANDARDS_FOR_DIM:
            sections.append(f"## {dim.title()}\n\n{compact}")
    return "\n\n".join(sections) if sections else _NO_STANDARDS


def build_consolidated_prompt(
    dimensions: list[str],
    context: PromptContext,
    template: str | None = None,
) -> str:
    """Build a multi-dimension analysis prompt with all standards inline."""
    if template is None:
        template = load_template(template_name="consolidated.md")

    standards_text = _render_all_standards(
        context.standards_dir, dimensions, context.work_dir,
    ) if context.standards_dir else _NO_STANDARDS

    manifest_context = _render_manifest_context(context)
    prompt_hash = _template_hash(template)

    values = {
        _TPL_DISCIPLINE: context.language,
        _TPL_REPO_NAME: context.repo_name,
        _TPL_DATE: context.date_str,
        _TPL_DIMENSION_LIST: ", ".join(dimensions),
        _TPL_SOURCE_FILE_COUNT: str(context.source_file_count),
        _TPL_STANDARDS_CHECKLISTS: standards_text,
        _TPL_ANALYSIS_GUIDANCE: manifest_context,
        _TPL_PROMPT_HASH: prompt_hash,
        _TPL_SOURCE_MANIFEST: manifest_context,
    }
    if context.extra_vars:
        values.update(context.extra_vars)
    return render_template(template, values)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/engine/test_prompt_builder.py -v`
Expected: All tests pass including the new one.

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/data/prompts/consolidated.md src/quodeq/analysis/prompts/builder.py tests/engine/test_prompt_builder.py
git commit -m "feat: consolidated prompt template for multi-dimension evaluation"
```

---

### Task 10: Evidence parser — split JSONL by dimension

**Files:**
- Modify: `src/quodeq/core/evidence/parser.py`
- Test: existing evidence parser tests (extend)

- [ ] **Step 1: Read current `parse_jsonl_to_evidence` to understand single-dimension flow**

Read: `src/quodeq/core/evidence/parser.py`

- [ ] **Step 2: Write failing test for `parse_jsonl_to_evidence_by_dimension`**

Test: create a JSONL file with findings from 2 dimensions (e.g., `req="S-CON-1"` and `req="M-MOD-1"`). Call `parse_jsonl_to_evidence_by_dimension(...)` and verify it returns `{"security": Evidence(...), "maintainability": Evidence(...)}` with correct findings in each.

- [ ] **Step 3: Implement `parse_jsonl_to_evidence_by_dimension`**

New function that:
1. Reads all JSONL entries
2. Groups by dimension (derived from `d` field or req ID prefix)
3. Calls `parse_jsonl_to_evidence` per group (or builds Evidence directly)
4. Returns `dict[str, Evidence]`

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v -k "evidence"`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/core/evidence/parser.py tests/
git commit -m "feat: parse_jsonl_to_evidence_by_dimension for consolidated mode"
```

---

### Task 11: Consolidated runner path + opt-out flag

**Files:**
- Modify: `src/quodeq/analysis/runner.py:252-283`
- Modify: `src/quodeq/analysis/subagents/runner.py`
- Modify: `src/quodeq/cli_parser.py`
- Modify: `src/quodeq/cli.py`

- [ ] **Step 1: Add `--no-consolidated` flag to CLI**

In `src/quodeq/cli_parser.py`, add:

```python
parser.add_argument(
    "--no-consolidated", action="store_true",
    help="Disable multi-dimension consolidation (evaluate dimensions separately)",
)
```

- [ ] **Step 2: Add `consolidated` field to `AnalysisOptions`**

In `src/quodeq/analysis/runner.py`, add to `AnalysisOptions`:

```python
consolidated: bool = True
```

Wire it in `src/quodeq/cli.py`:

```python
consolidated=not getattr(args, 'no_consolidated', False) and not bool(os.environ.get("QUODEQ_NO_CONSOLIDATE")),
```

- [ ] **Step 3: Create `process_consolidated_dimensions` in subagents/runner.py**

New function that:
1. Lists source files (same as `_list_source_files`)
2. Builds consolidated prompt via `build_consolidated_prompt`
3. Creates FileQueue with adaptive files-per-agent
4. Launches SubagentPool with `dimensions=dimensions`
5. Collects results and calls `parse_jsonl_to_evidence_by_dimension`
6. Returns `dict[str, Evidence]`

- [ ] **Step 4: Wire consolidated mode in `_run_dimensions`**

In `src/quodeq/analysis/runner.py`, modify `_run_dimensions`:

```python
def _run_dimensions(config: RunConfig) -> dict[str, Evidence]:
    dimensions, ctx = load_analysis_context(config)
    emit_marker("setup", dimensions=dimensions)

    # Consolidated mode: evaluate all dimensions in one pass
    if config.options.consolidated and len(dimensions) > 1 and config.options.max_subagents > 1:
        return _process_consolidated(config, dimensions, ctx)

    # Per-dimension loop (fallback)
    result: dict[str, Evidence] = {}
    # ... existing code ...
```

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/analysis/runner.py src/quodeq/analysis/subagents/runner.py src/quodeq/cli_parser.py src/quodeq/cli.py
git commit -m "feat: consolidated multi-dimension evaluation path with opt-out flag"
```

---

### Task 12: Phase 2 integration test

**Files:**
- Test: `tests/engine/test_consolidated_integration.py` (create)

- [ ] **Step 1: Write integration test for consolidated mode**

Test that:
1. Create compiled standards for 2 dimensions
2. Mock `run_analysis` to write findings with both `S-CON-*` and `M-MOD-*` req IDs
3. Call the consolidated runner path
4. Verify result is `dict[str, Evidence]` with correct dimension keys
5. Verify findings are split correctly

- [ ] **Step 2: Write integration test for `--no-consolidated` fallback**

Test that when `consolidated=False`, the per-dimension loop runs even with multiple dimensions.

- [ ] **Step 3: Run tests**

Run: `pytest tests/engine/test_consolidated_integration.py -v`
Expected: All tests pass.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/engine/test_consolidated_integration.py
git commit -m "test: integration tests for consolidated multi-dimension evaluation"
```

---

## Summary

| Task | Phase | Description | Key files |
|------|-------|-------------|-----------|
| 1 | 1 | Adaptive files-per-agent | `subagents/runner.py` |
| 2 | 1 | Scout-then-scale pool | `subagents/pool.py` |
| 3 | 1 | Rename n_subagents → max_subagents | `runner.py`, `cli.py`, `cli_parser.py` |
| 4 | 1 | Web API + UI for maxSubagents | `base.py`, `routes.py`, UI components |
| 5 | 1 | Phase 1 integration test | test file |
| 6 | 2 | Multi-dim MCP args + refs | `mcp/args.py`, `standards/refs.py` |
| 7 | 2 | Multi-dim FindingsRouter | `mcp/findings_server.py` |
| 8 | 2 | Multi-dim AnalysisConfig + pool | `subprocess.py`, `pool.py` |
| 9 | 2 | Consolidated prompt template | `consolidated.md`, `builder.py` |
| 10 | 2 | Evidence parser split-by-dim | `evidence/parser.py` |
| 11 | 2 | Consolidated runner + opt-out | `runner.py`, `cli.py` |
| 12 | 2 | Phase 2 integration test | test file |

**Phase 1 (Tasks 1-5):** Ship independently. Immediate 70-80% savings for small/medium projects.
**Phase 2 (Tasks 6-12):** Ship after Phase 1 validated. Additional 83-95% savings for multi-dimension runs.
