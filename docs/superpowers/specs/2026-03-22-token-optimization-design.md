# Token Optimization — Adaptive Scaling & Multi-Dimension Consolidation

**Date:** 2026-03-22
**Status:** Draft

## Problem

Evaluating a 20-file subfolder on a single dimension consumed ~20% of a 5-hour company token budget. The root cause is not prompt size (rendered standards are only ~2-3K tokens per dimension) but the **number of AI CLI sessions** spawned. Each session carries ~8K tokens of fixed overhead (system prompt, tool schemas, analysis prompt) before reading a single file.

Current defaults:
- `n_subagents = 5` (hardcoded CLI default, not configurable from web UI)
- All 5 agents launch immediately regardless of project size
- Each dimension runs as a separate round of agents
- Files are re-read from scratch for every dimension

For 20 files on 1 dimension: 5 sessions processing ~4 files each.
For 200 files on 6 dimensions: 30 sessions, same files read 6 times.
For 5000 files on 6 dimensions: `_MAX_FILES_PER_AGENT = 30` forces context rotation — each agent dies after 30 files and a new session spawns. That's `ceil(5000/30) = 167` agent sessions per dimension round, × 6 dimensions = **~1000 sessions**, each with ~8K tokens fixed overhead = **~8M tokens in session overhead alone**.

## Design

Two phases, each independently shippable.

---

## Phase 1: Adaptive Agent Scaling

**Goal:** Don't spawn agents unless the workload justifies it.

### 1.1 Scout-then-scale pool strategy

Replace the current "launch all N agents at once" behavior with a two-phase pool:

**Phase 1 — Scout:** Launch 1 agent. It processes its first batch from the file queue (up to `_MAX_FILES_PER_AGENT = 30` files).

**Phase 2 — Scale:** When the scout completes, check the remaining queue:
- If `remaining <= _MAX_FILES_PER_AGENT` → respawn 1 agent to drain the rest (or none if queue is empty)
- If `remaining > _MAX_FILES_PER_AGENT` → compute overflow: `min(max_subagents - 1, ceil(remaining / _MAX_FILES_PER_AGENT))` and launch that many agents concurrently

**Phase 3 — Drain:** Existing respawn-on-completion logic handles stragglers.

#### Files changed

**`src/quodeq/analysis/subagents/pool.py`**

- `SubagentPool.__init__`: `n_agents` semantically becomes a ceiling (`max_agents`). Add internal `_launched_scout: bool = False` state.
- `SubagentPool._run_pool_loop`: Start with 1 agent. After first future completes, call `_compute_scale_up()` to determine overflow count. Submit overflow agents. Rest of loop (respawn on completion) stays the same.
- New method `_compute_scale_up(remaining: int) -> int`:
  ```
  needed = ceil(remaining / _MAX_FILES_PER_AGENT)
  return min(needed, self._max - 1)
  ```

**`src/quodeq/analysis/subagents/runner.py`**

- No changes to `_launch_pool` or `_run_verification_pool` signatures. The pool internally decides how many agents to actually use.
- Verification pool: also apply adaptive scaling (respect `max_subagents`).

### 1.2 `max_subagents` setting exposed to web UI

**`src/quodeq/services/base.py`**
- Add `max_subagents: int = 5` to `EvaluationOptions`.

**`src/quodeq/services/evaluation_mixin.py`**
- `_build_evaluate_cmd`: pass `--n-subagents <value>` when `options.max_subagents` is set.

**`src/quodeq/api/routes.py`**
- Accept `maxSubagents` from the evaluation payload (default 5, min 1, max 10).
- Pass to `EvaluationOptions(max_subagents=...)`.

**`ui/web/`** (React)
- Add "Max parallel agents" number input to the evaluation settings panel.
- Default 5, range 1-10.
- Send as `maxSubagents` in the evaluation API call.

### 1.3 Adaptive files-per-agent for large projects

The current `_MAX_FILES_PER_AGENT = 30` forces context rotation — when an agent reaches 30 files, `take()` returns empty, the agent CLI session ends, and the pool respawns a fresh session. For large projects (5000 files, 5 concurrent agents) this means `ceil(5000/30) = 167` total sessions per dimension round.

Each context rotation carries the full ~8K token fixed overhead of a new CLI session. The 30-file limit was chosen conservatively for context window management, but since findings are reported via MCP tool calls (not accumulated in the response), the context grows mainly from file-read history and tool call overhead.

**New behavior:** Compute `max_files_per_agent` adaptively based on the total file count:

```
if total_files <= 50:
    max_files_per_agent = total_files  # no rotation needed
elif total_files <= 200:
    max_files_per_agent = 50
elif total_files <= 1000:
    max_files_per_agent = 75
else:
    max_files_per_agent = 100
```

This reduces respawn cycles:

| Files | Current (30/agent, total sessions) | Adaptive (total sessions) | Sessions saved |
|-------|--------------------------------------|---------------------------|----------------|
| 20 | 1 | 1 | 0 |
| 200 | ceil(200/30) = 7 | ceil(200/50) = 4 | ~40% |
| 1000 | ceil(1000/30) = 34 | ceil(1000/75) = 14 | ~60% |
| 5000 | ceil(5000/30) = 167 | ceil(5000/100) = **50** | **70%** |

#### Files changed

**`src/quodeq/analysis/subagents/runner.py`**
- New function `_compute_files_per_agent(total_files: int) -> int` with the tiered logic above.
- `process_dimension_with_subagents`: call `_compute_files_per_agent` when creating `FileQueue` instead of using `_MAX_FILES_PER_AGENT` constant.
- `_MAX_FILES_PER_AGENT` remains as a fallback/cap constant.

**`src/quodeq/analysis/subagents/file_queue.py`**
- No changes. Already accepts `max_files_per_agent` as a constructor parameter.

### 1.4 Expected impact (Phase 1)

| Scenario | Before (sessions) | After (sessions) | Savings |
|----------|-------------------|-------------------|---------|
| 20 files, 1 dim | 5 | **1** | 80% |
| 50 files, 1 dim | 5 | **2** | 60% |
| 100 files, 1 dim | 5 | **4** | 20% |
| 150+ files, 1 dim | 5 | **5** | 0% |
| 20 files, 6 dims | 30 | **6** | 80% |
| 5000 files, 1 dim | 167 | **50** | 70% |
| 5000 files, 6 dims | ~1000 | **~300** | 70% |

---

## Phase 2: Multi-Dimension Consolidation

**Goal:** Evaluate all selected dimensions in a single pass so files are read once, not once per dimension.

### 2.1 Consolidated prompt template

New template: `src/quodeq/data/prompts/consolidated.md`

Structure:
```markdown
# Code Quality Analysis — Quodeq

You are evaluating **{{REPO_NAME}}** across these dimensions: {{DIMENSION_LIST}}

{{SOURCE_MANIFEST}}

## Workflow (subagent mode)
1. Call `get_next_files()` for your next batch
2. Read each file
3. Evaluate against ALL dimension checklists below
4. Call `report_finding()` for every finding (the req ID encodes the dimension)
5. Repeat until no more files

## report_finding parameters
(same as current subagent.md)

## Standards Checklists

{{STANDARDS_CHECKLISTS}}
```

The `{{STANDARDS_CHECKLISTS}}` placeholder renders all selected dimensions sequentially:
```
## Security
S-CON-1: ...
S-CON-2: ...

## Maintainability
M-MOD-1: ...
...
```

Total standards across all 6 dimensions: ~5.3K tokens. This fits easily in a single prompt.

### 2.2 Runner changes

**`src/quodeq/analysis/runner.py`**

Currently `_run_dimensions` iterates dimensions sequentially, each getting its own agent pool:
```python
for idx, dimension in enumerate(dimensions, 1):
    ev = _process_single_dimension(config, dimension, idx, ctx)
```

New consolidated path:
```python
if consolidated_mode:
    ev_dict = _process_all_dimensions_consolidated(config, dimensions, ctx)
else:
    # existing per-dimension loop (fallback)
```

`_process_all_dimensions_consolidated`:
1. Build one prompt with all dimension standards
2. Create one file queue with all source files
3. Launch adaptive pool (Phase 1 logic)
4. Agents report findings with dimension-specific req IDs (`S-CON-3`, `M-MOD-1`)
5. Parse evidence JSONL, split by dimension (req ID prefix determines dimension)
6. Return `dict[str, Evidence]`

**`src/quodeq/analysis/prompts/builder.py`**

- New function `build_consolidated_prompt(template, dimensions, context)` that renders standards for all dimensions into one prompt.
- Reuses existing `render_compact_standards` per dimension, concatenated with dimension headers.

### 2.2b MCP server and evidence pipeline changes

The current MCP server and evidence parser are **single-dimension by design**. Consolidated mode requires changes across the pipeline:

**`src/quodeq/analysis/mcp/findings_server.py`**
- `FindingsRouter.__init__`: Accept a list of dimensions instead of a single dimension. Load compiled requirements and refs for ALL selected dimensions.
- `FindingsRouter._enrich()`: Currently auto-fills dimension from `self._dimension` (a single value). Must instead **derive dimension from the req ID prefix** (e.g., `S-CON-3` → `security`, `M-MOD-1` → `maintainability`). The req ID prefix-to-dimension mapping is deterministic and can be built at init time from the compiled standards.

**`src/quodeq/analysis/mcp/args.py`**
- Accept `--dimension` as a comma-separated list (e.g., `--dimension security,maintainability,reliability`) instead of a single value.

**`src/quodeq/core/standards/refs.py`**
- `load_compiled_requirements` and `load_compiled_refs`: Add multi-dimension variants that load and merge requirements from multiple dimension JSON files. Or change the existing functions to accept `list[str]` instead of `str`.

**`src/quodeq/analysis/subprocess.py`**
- `AnalysisConfig.dimension` field: Change from `dimension: str | None = None` to `dimensions: list[str] | None = None` (or keep as `str | None` with comma-separated values for simplicity — comma-separated is preferred since it flows directly to CLI args).
- `_create_mcp_config`: Pass comma-separated dimensions to the MCP server args when in consolidated mode.
- `_build_ai_cmd`: Pass `config.dimensions` (comma-separated string) through to `_create_mcp_config`.

**`src/quodeq/core/evidence/parser.py`**
- Current `parse_jsonl_to_evidence` takes dimension from the first judgment and applies to all. In consolidated mode, a single JSONL file contains findings from multiple dimensions.
- New function `parse_jsonl_to_evidence_by_dimension(jsonl_path, context, compiled_dir) -> dict[str, Evidence]` that splits JSONL entries by dimension (derived from req ID prefix) and produces per-dimension Evidence objects.

**`src/quodeq/analysis/subagents/pool.py`**
- `SubagentPool.__init__`: Accept `dimensions: list[str]` instead of `dimension: str` for consolidated mode. File naming uses a combined key (e.g., `consolidated_evidence.jsonl` instead of `{dimension}_evidence.jsonl`).
- `_build_agent_config`: Pass all dimensions to `AnalysisConfig`.
- `_shared_jsonl_path` and stream file naming: Use `consolidated` prefix when in multi-dimension mode.

**`src/quodeq/analysis/subagents/runner.py`**
- New function `process_consolidated_dimensions(config, dimensions, ctx)` that:
  1. Builds the consolidated prompt with all dimension standards
  2. Creates a single file queue
  3. Launches the adaptive pool with `dimensions=dimensions`
  4. Collects evidence and splits by dimension
  5. Returns `dict[str, Evidence]`

### 2.3 When to use consolidated mode

Consolidated mode is the new default when `len(dimensions) > 1`. The per-dimension loop remains as a fallback (single dimension, or explicit opt-out).

Decision matrix:
- 1 dimension selected → per-dimension path (simpler prompt, current behavior)
- 2+ dimensions selected → consolidated path

### 2.4 Interaction with adaptive scaling

Phase 1 and Phase 2 compose naturally:
- Consolidated mode produces 1 file queue for all dimensions
- Adaptive scaling decides how many agents that queue needs
- Result: 20 files, 6 dimensions → **1 session** (instead of 30)

### 2.5 Expected impact (Phase 1 + Phase 2 combined)

| Scenario | Before (sessions) | Phase 1 only | Phase 1+2 | Total savings |
|----------|-------------------|-------------|-----------|---------------|
| 20 files, 1 dim | 5 | 1 | 1 | 80% |
| 20 files, 6 dims | 30 | 6 | **1** | **97%** |
| 200 files, 1 dim | 5 | 5 | 5 | 0% |
| 200 files, 6 dims | 30 | 30 | **5** | **83%** |
| 1000 files, 6 dims | ~200 | ~84 | **~14** | **93%** |
| 5000 files, 1 dim | 167 | 50 | 50 | 70% |
| 5000 files, 6 dims | ~1000 | ~300 | **~50** | **95%** |

**Breakdown for 5000 files, 6 dims (worst case today):**
- Before: 167 sessions/dim × 6 dims = ~1000 sessions, ~8M tokens overhead
- Phase 1 (adaptive files/agent): 50 sessions/dim × 6 dims = ~300 sessions, ~2.4M tokens
- Phase 1+2 (consolidated): 50 sessions × 1 pass = ~50 sessions, ~400K tokens overhead
- File reads: 5000 × 6 = 30,000 reads → 5000 × 1 = 5,000 reads (saving ~12.5M tokens at 500 tok/file avg)

Total estimated savings for 5000 files, 6 dims: **~18M tokens → ~2.5M tokens (86% reduction)**.

---

## What stays the same

- **compass.md template** — single-agent path (`n_subagents=1` from CLI) is unchanged and continues to use the per-dimension loop with compass.md. Phase 2 consolidated mode only applies to the subagent pool path.
- **subagent.md template** — used for single-dimension subagent runs (when 1 dimension selected)
- **Standards data files** — no changes to compiled JSONs
- **FileQueue** — unchanged
- **Report generation** — already splits evidence by dimension downstream
- **Output quality** — same standards, same reporting granularity

## Important clarifications

### `n_subagents=1` (single-agent CLI path)

When `n_subagents=1` (the `AnalysisOptions` default), `runner.py:237` takes a completely different code path: no pool, no file queue, no `get_next_files` — it uses `compass.md` with Grep-first strategy. This path is **unchanged** by Phase 1 or Phase 2.

The web UI default is `max_subagents=5` which means web-launched evaluations always go through the subagent pool path. The adaptive scaling in Phase 1 may decide to run only 1 agent, but it still uses `subagent.md` with the file queue workflow — it doesn't fall back to the `compass.md` path.

### Naming: `n_subagents` vs `max_subagents`

- `AnalysisOptions.n_subagents` (runner.py) — rename to `max_subagents` to reflect that it's now a ceiling, not a fixed count.
- `EvaluationOptions.max_subagents` (base.py) — new field, consistent naming.
- CLI flag `--n-subagents` (cli_parser.py) — keep for backward compatibility, add `--max-subagents` as preferred alias.
- `_build_evaluate_cmd` passes `--n-subagents` to the CLI subprocess (new, currently not passed at all).

### Consolidated mode opt-out

Add `--no-consolidated` CLI flag and `QUODEQ_NO_CONSOLIDATE=1` env var to explicitly opt out of consolidated mode. This enables A/B testing and provides a rollback mechanism.

### Scout timeout fallback

If the scout agent runs longer than **3 minutes** (or 50% of `max_duration / max_agents`, whichever is smaller) and the queue still has more than `max_files_per_agent` files remaining, spawn overflow agents without waiting for the scout to complete. Implemented in `SubagentPool._run_pool_loop` by checking elapsed time during the existing poll loop (`_FUTURE_POLL_INTERVAL_S = 0.5s`). When the timeout triggers, submit overflow agents from within the poll loop — no secondary timer thread needed since the poll loop already runs continuously.

## Risks

| Risk | Mitigation |
|------|------------|
| Multi-dim prompt confuses LLM (lower quality) | Phase 2 behind feature flag; A/B test on known repos before default |
| Agent processes fewer findings per dimension when juggling multiple | Monitor findings-per-file ratio before vs after |
| Scout agent takes long, delaying scale-up | Time-based fallback: if scout runs > X minutes and queue > threshold, spawn overflow without waiting for completion |
| Standards for all 6 dims too large for prompt | Currently ~5.3K tokens total — well within limits. Monitor if standards grow. |
| Higher files-per-agent degrades quality on later files (context pressure) | Monitor findings-per-file ratio at different batch sizes; keep 100 as hard cap; the MCP-based reporting means findings don't accumulate in context |
| 5K file projects hit API rate limits with fewer, longer sessions | Longer sessions make fewer API calls total; this should improve rate limit behavior |
| Multi-dim prompt degrades quality on smaller subagent models | `QUODEQ_SUBAGENT_MODEL` can override to cheaper models; A/B test must include these. At 5.3K tokens for all standards, even smaller models should handle it, but monitor findings quality |

## Testing

### Phase 1
- Unit tests: `_compute_scale_up` with various file counts and max_agents values
- Unit tests: `_compute_files_per_agent` returns correct tiers for 20, 100, 500, 5000 files
- Integration test: 20-file project → verify only 1 agent session created (no pool)
- Integration test: 200-file project → verify scout-then-scale behavior
- Integration test: `max_subagents` API parameter flows through to CLI subprocess
- Web UI test: settings panel sends `maxSubagents` in API payload

### Phase 2
- Unit test: consolidated prompt includes all dimension standards
- Unit test: evidence JSONL with mixed-dimension req IDs parses into correct per-dimension Evidence
- Integration test: consolidated prompt → verify findings split correctly by dimension
- Quality test: compare finding counts and quality consolidated vs per-dimension on a reference project (before enabling as default)
