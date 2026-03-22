# File Prioritization & Configurable Pool Budget

**Date:** 2026-03-22
**Status:** Draft

**Dependency:** Requires the `feat/token-optimization` branch (PR #107) for `process_consolidated_dimensions` and `max_subagents` plumbing.

## Problem

For large projects (4K+ files), agents hit their time/turn budget before reading all files. Currently files are fed in alphabetical order — config files in `a/` get analyzed before critical source files in `s/`. When budget runs out, important files may never be evaluated, reducing score quality.

Additionally, the pool budget (10 minutes) is hardcoded with no user control.

## Design

Two independent features, both affecting evaluation quality for large projects.

---

## Feature 1: Dimension-Aware File Prioritization

### Scoring Model

Each file gets a priority score computed from multiple signals at prescan time. Five signal layers, each contributing to the final score:

#### Layer 1: Base Score (0-10) — project-type-aware, same for all dimensions

- **Path pattern** (0-5): `src/`, `lib/`, `app/`, `core/` → 5; `pkg/`, `internal/` → 4; `test/`, `tests/` → 1; `docs/`, `scripts/` → 0. Default for unmatched paths: 2.
- **Entry point pattern** (0-3): files matching `main.*`, `app.*`, `index.*`, `routes.*`, `server.*` → 3
- **Category boost** (0-2): discipline-detected category (backend, mobile, frontend) boosts files matching category-specific patterns (e.g., `controller`, `service` for backend; `activity`, `fragment` for mobile). Category is accessed via `config.target.category` (for per-target runs) or `config.manifest.category` (delegates to primary target). For multi-target repos, use the target's own category when available.

#### Layer 2: Dimension Boost (0-5) — varies per dimension being evaluated

- `security`: files matching auth/crypto/route/handler/validation/permission/secret patterns → +5
- `reliability`: files matching error/exception/retry/fallback/timeout/database/migration/health patterns → +5
- `maintainability`: boost by file size — score = `min(5, file_size_bytes / 2000)` (files >10KB get full +5, proportional below)
- `performance`: files matching cache/query/database/pool/batch/stream/index/optimize patterns → +5
- `flexibility`: files matching config/plugin/adapter/factory/interface/abstract/registry patterns → +5
- `usability`: files matching accessibility/a11y/i18n/locale/form/input/validation patterns → +5

**Consolidated mode**: `dimension_boost = max(boost across all selected dimensions)`.

#### Layer 3: Import Fan-In (0-5) — how many other files depend on this one

A single grep pass across the codebase counts how many times each filename (without extension) appears in `import`/`require`/`from` statements. Files imported by many others are structural hubs and more likely to propagate quality issues.

- Score: `min(5, fan_in_count / 3)` — files imported by 15+ others get full +5

**Implementation**: One `grep -r` pass (or equivalent Python scan) collecting all import-like statements, extracting module names, and counting references per source file. Runs once at prescan time. For languages without clear import syntax, skip this layer (score 0).

**Language patterns to match**:
- Python: `from X import`, `import X`
- JavaScript/TypeScript: `import ... from 'X'`, `require('X')`
- Java/Kotlin: `import X.Y.Z`
- Go: `import "X"`
- Swift: `import X`

#### Layer 4: Git History Signals (0-5) — churn and recency

When git is available (`.git/` exists), a single `git log --name-only --since="3 months"` pass collects:
- **Churn**: how many commits touched each file
- **Recency**: when the file was last modified

Score: `min(5, churn_count / 4)` — files changed 20+ times in 3 months get full +5. A recency multiplier of 1.5x applies to files changed in the last 2 weeks.

**Fallback**: If git is not available (e.g., analyzing a downloaded archive), this layer scores 0 for all files. No error, no warning.

**Implementation**: Single `git log` call, parse output. Cached for the evaluation run.

#### Layer 5: Previous Violations Boost (0-5) — files with known issues

From the verification manifest (already loaded when `verify_findings=True`), files that had violations in the previous run get priority. Re-checking these first ensures regression detection.

Score: `min(5, previous_violation_count)` — files with 5+ prior violations get full +5.

**Implementation**: Reuse `load_previous_findings_for_dimension` from `subagents/verify.py`. Group by file, count violations per file. When running consolidated mode, merge across dimensions. When no previous run exists, this layer scores 0.

#### Total Score

```
total = base_score + dimension_boost + fan_in_score + git_score + previous_violations_score
```

Maximum theoretical: 10 + 5 + 5 + 5 + 5 = **30**.

Files are sorted by total score descending, then by path alphabetically as tiebreaker.

**Small projects (≤50 files)**: all files are analyzed regardless; ordering still applied but doesn't affect coverage since all files fit in agent budget.

### Config Data File

`src/quodeq/data/config/file_priority.json`:

```json
{
  "path_boost": {
    "src/": 5, "lib/": 5, "app/": 5, "core/": 5,
    "pkg/": 4, "internal/": 4,
    "test/": 1, "tests/": 1, "spec/": 1,
    "docs/": 0, "scripts/": 0, "tools/": 0
  },
  "default_path_score": 2,
  "entry_points": ["main.*", "app.*", "index.*", "routes.*", "server.*"],
  "entry_point_boost": 3,
  "category_keywords": {
    "backend": ["controller", "service", "handler", "middleware", "router", "repository"],
    "mobile": ["activity", "fragment", "viewmodel", "screen", "widget", "composable"],
    "frontend": ["component", "page", "hook", "store", "reducer", "context"]
  },
  "category_keyword_boost": 2,
  "dimension_keywords": {
    "security": ["auth", "login", "crypto", "token", "session", "password", "secret", "sanitiz", "validat", "permission", "route", "handler", "middleware"],
    "reliability": ["error", "exception", "retry", "fallback", "timeout", "recovery", "health", "monitor", "migration", "database", "circuit"],
    "maintainability": [],
    "performance": ["cache", "query", "database", "pool", "batch", "stream", "index", "optimize", "buffer"],
    "flexibility": ["config", "plugin", "adapter", "factory", "interface", "abstract", "registry", "provider"],
    "usability": ["accessibility", "a11y", "i18n", "locale", "input", "form", "validation", "aria"]
  },
  "dimension_keyword_boost": 5,
  "maintainability_size_divisor": 2000,
  "fan_in_divisor": 3,
  "fan_in_max": 5,
  "git_churn_divisor": 4,
  "git_churn_max": 5,
  "git_recency_days": 14,
  "git_recency_multiplier": 1.5,
  "git_lookback_months": 3,
  "previous_violations_max": 5,
  "import_patterns": {
    "python": ["^\\s*(?:from|import)\\s+(\\S+)"],
    "javascript": ["(?:import|require)\\s*\\(?['\"]([^'\"]+)"],
    "java": ["^\\s*import\\s+([\\w.]+)"],
    "go": ["\"([^\"]+)\""],
    "swift": ["^\\s*import\\s+(\\w+)"]
  }
}
```

All thresholds and boost values are tunable without code changes.

### Integration Point

**`src/quodeq/analysis/subagents/priority.py`** (new module) — scoring logic:
- `prioritize_files(files, src, dimension, category, evidence_dir=None) -> list[str]`
- For consolidated mode: `dimension` parameter accepts `list[str]`, scoring takes `max(boost)` across dimensions
- Loads config via `lru_cache`
- Each signal layer is a separate function for testability
- `_compute_base_score(filepath, config, category)`
- `_compute_dimension_boost(filepath, dimension, config, file_size)`
- `_compute_fan_in(files, src, config)` — returns `dict[str, int]` (one pass)
- `_compute_git_scores(files, src, config)` — returns `dict[str, float]` (one pass)
- `_compute_previous_violations(evidence_dir, dimension)` — returns `dict[str, int]`

**`src/quodeq/analysis/subagents/runner.py`** — call `prioritize_files()`:
- In `_list_source_files`: currently returns `(files, extensions)`. After this change, sort files via `prioritize_files()` before returning. Access dimension via the `dim_id` parameter. Access category via `config.target.category` if target exists, else `config.manifest.category`.
- In `process_consolidated_dimensions` (from token-optimization branch): same, passing `dimensions` list.

### Files Changed

**New files:**
- `src/quodeq/data/config/file_priority.json` — scoring rules and thresholds
- `src/quodeq/analysis/subagents/priority.py` — scoring logic (separate module, keeps runner.py focused)

**Modified files:**
- `src/quodeq/analysis/subagents/runner.py` — call `prioritize_files()` in `_list_source_files` and `process_consolidated_dimensions`

**Unchanged:**
- `FileQueue`, `SubagentPool`, prompt templates, MCP server, evidence parser — unaffected. The file list is just reordered before being fed to the queue.

### Cost

Zero extra AI tokens. All scoring runs in pure Python at prescan time before any AI sessions start:
- Path/keyword scoring: instant
- File size checks: `os.path.getsize()` per file — fast, no file reads
- Import fan-in: one grep-like pass across source files — a few seconds for 4K files
- Git history: one `git log` call — typically <2 seconds
- Previous violations: already loaded for verification — no extra I/O

Total prescan overhead: estimated 2-5 seconds for a 4K-file project.

---

## Feature 2: Configurable Pool Budget

### Current State

- `_DEFAULT_POOL_BUDGET = 600` (10 min) hardcoded in `pool.py`
- `SubagentPool.run()` uses `self._base_config.max_duration or _DEFAULT_POOL_BUDGET` — conflating pool budget with per-agent duration
- `_build_agent_config` also uses `max_duration` for per-agent timeout
- Per-agent duration (`--max-duration`, default 30 min) is CLI-configurable but separate
- Pool budget is not configurable from CLI, API, or web UI

### Splitting pool_budget from max_duration

Currently `max_duration` does double duty:
1. **Pool budget** — total time the pool can run (used in `run()` line 263 and `_should_respawn` line 181)
2. **Per-agent timeout** — how long a single agent can run (used in `_build_agent_config` line 102)

This must be split into two separate fields:
- `pool_budget: int` — total pool time (new field, default 600)
- `max_duration: int` — per-agent timeout (existing field, keeps current behavior)

In `SubagentPool.run()`: use `config.pool_budget` for the pool loop time limit.
In `_build_agent_config`: keep using `config.max_duration` for per-agent timeout (unchanged).
In `_should_respawn`: use `pool_budget` (passed as parameter from `run()`), not `max_duration`.

### New Behavior

- **CLI flag**: `--pool-budget <seconds>` (default 600, range 60-3600)
- **Env var**: `QUODEQ_POOL_BUDGET` (clamped to 60-3600, same as CLI)
- **`AnalysisOptions`**: new field `pool_budget: int | None = None`
- **`AnalysisConfig`**: new field `pool_budget: int = 600`
- **`SubagentPool.run()`**: use `config.pool_budget` for pool loop time limit
- **`SubagentPool._should_respawn()`**: receives pool_budget instead of max_duration
- **API route**: accept `poolBudget` from evaluation payload (seconds, clamped 60-3600)
- **`EvaluationOptions`**: new field `pool_budget: int = 600`
- **`_build_evaluate_cmd`**: pass `--pool-budget` when non-default. Note: other flags like `--max-turns` and `--max-duration` are currently passed via environment variables, not CLI args. `--pool-budget` follows the same env var pattern (`QUODEQ_POOL_BUDGET`) but also adds the CLI flag for direct use.
- **`_build_eval_env`**: set `QUODEQ_POOL_BUDGET` env var when non-default.
- **Web settings**: "Analysis time limit" number input (minutes), range 1-60, default 10. Stored in localStorage as `cc-pool-budget` (in seconds). Sent as `poolBudget` in API payload.

### Files Changed

- `src/quodeq/analysis/subprocess.py` — add `pool_budget: int = 600` to `AnalysisConfig`
- `src/quodeq/analysis/subagents/pool.py` — `run()` uses `config.pool_budget`; `_should_respawn` and `_run_pool_loop` receive pool_budget; `_build_agent_config` keeps using `max_duration` for per-agent timeout
- `src/quodeq/analysis/runner.py` — add `pool_budget` to `AnalysisOptions`, wire to `AnalysisConfig`
- `src/quodeq/cli_parser.py` — add `--pool-budget` flag
- `src/quodeq/cli.py` — wire flag + env var (CLI flag takes precedence over env var)
- `src/quodeq/services/base.py` — add `pool_budget` to `EvaluationOptions`
- `src/quodeq/services/evaluation_mixin.py` — set `QUODEQ_POOL_BUDGET` in `_build_eval_env` when non-default
- `src/quodeq/api/routes.py` — accept `poolBudget` from payload, clamp 60-3600
- `src/quodeq/ui/src/features/settings/components/SettingsPage.jsx` — add time limit input
- `src/quodeq/ui/src/features/evaluation/hooks/useEvaluation.js` — send `poolBudget` in payload

---

## Feature 3: Incremental Analysis (Diff-Based Re-evaluation)

### Problem

When re-evaluating a project, the current system analyzes all files from scratch — even if only 50 out of 4000 changed. For repeat evaluations (the common case in CI/CD or active development), this wastes 95%+ of tokens re-reading unchanged files that will produce the same findings.

### Core Idea

On re-evaluation, determine which files changed since the last run. Only send changed files (and their dependents) to the AI agents. Carry forward cached findings for all unchanged files. Merge both into the final Evidence.

### Evaluation Fingerprint

Each evaluation stores a fingerprint alongside its evidence:

**`evaluation_fingerprint.json`** (in the run's evidence directory):
```json
{
  "git_commit": "abc123def",
  "file_hashes": {
    "src/auth.py": "sha256:...",
    "src/routes.py": "sha256:...",
    ...
  },
  "standards_checksum": "sha256:...",
  "timestamp": "2026-03-22T20:00:00Z"
}
```

- **Git commit**: primary diff mechanism when available
- **File hashes**: fallback for non-git repos, and for verifying git diff accuracy (handles rebases/force-pushes)
- **Standards checksum**: hash of compiled standards JSON — if standards change, all files need re-analysis

### Change Detection

On a new evaluation, compare against the most recent previous fingerprint:

1. **If git available and commit exists**: `git diff --name-only <prev_commit>..HEAD` → changed files. Fast (milliseconds).
2. **If git unavailable or commit missing**: compare file hashes — rehash all files, diff against stored hashes. Slower but reliable.
3. **If no previous fingerprint exists**: full analysis (first run).
4. **If standards checksum changed**: full analysis (rules changed, all findings potentially invalid).

### File Classification

After change detection, classify every source file into one of three buckets:

| Bucket | Action | Source |
|--------|--------|--------|
| **Changed** | Re-analyze fully | git diff or hash comparison |
| **Dependent** | Re-analyze fully | Import graph: files that import a changed file (1 level deep) |
| **Unchanged** | Carry forward findings | Everything else |

The import graph from Feature 1 (Layer 3) is reused here — computed once, used for both prioritization and dependency cascade.

### Findings Cache & Carry-Forward

For unchanged files:
1. Load previous run's JSONL evidence
2. Filter to findings whose `file` is in the unchanged set
3. Copy these findings directly into the new run's JSONL (before agents start)
4. These findings appear on the dashboard immediately — no AI cost

For changed + dependent files:
1. Feed them to the file queue (prioritized per Feature 1)
2. AI agents analyze them normally
3. New findings are written via MCP as usual

After agents finish:
1. Merge: carried-forward findings + new findings = complete evidence
2. Deduplicate (existing dedup logic handles this)

### Cache Invalidation Rules

Carry-forward findings are invalidated (file moves to "changed" bucket) when:
- The file itself changed (content hash differs)
- A direct import dependency changed (1 level deep — not transitive, to keep it bounded)
- The compiled standards changed (standards checksum differs → full re-analysis)

**Not invalidated by**:
- Changes to unrelated files
- Changes to test files (tests don't cascade)
- Time alone (findings don't expire)

### Interaction with Verification

The existing verification pool re-checks previous findings against current code. With incremental analysis:
- **Unchanged files**: skip verification entirely — findings are known-good
- **Changed files**: verification is redundant since we're doing full re-analysis
- **Net effect**: verification pool can be skipped entirely in incremental mode, saving even more tokens

### UI Integration

- **Web dashboard**: "Re-scan changes" button alongside the existing "Run evaluation" button
- **CLI**: `--incremental` flag (default off for backward compat; could become default later)
- **API**: `incremental: true` in evaluation payload
- **Dashboard display**: show which findings are "cached" vs "new" — e.g., a subtle indicator or separate count

### Files Changed

**New files:**
- `src/quodeq/analysis/fingerprint.py` — build/compare/store evaluation fingerprints
- `src/quodeq/analysis/incremental.py` — change detection, file classification, findings carry-forward

**Modified files:**
- `src/quodeq/analysis/runner.py` — incremental path in `_run_dimensions`: detect changes, carry forward, analyze only changed files
- `src/quodeq/analysis/subagents/runner.py` — accept filtered file list (changed + dependents only)
- `src/quodeq/cli_parser.py` — add `--incremental` flag
- `src/quodeq/cli.py` — wire flag
- `src/quodeq/analysis/runner.py` — `AnalysisOptions` gets `incremental: bool = False`
- `src/quodeq/api/routes.py` — accept `incremental` from payload
- `src/quodeq/services/base.py` — `EvaluationOptions` gets `incremental: bool = False`
- Web UI: add "Re-scan changes" button

### Expected Impact

| Scenario | Full Analysis | Incremental |
|----------|--------------|-------------|
| 4000 files, 50 changed, 1 dim | 80 sessions | **1-2 sessions** |
| 4000 files, 50 changed, 6 dims | 80 sessions | **1-2 sessions** |
| 4000 files, 500 changed, 6 dims | 80 sessions | **~12 sessions** |
| First evaluation (no cache) | 80 sessions | 80 sessions (falls back to full) |

Token savings on repeat evaluations: **90-98%** for typical development cycles (small changes relative to project size).

---

## Testing

### File Prioritization
- Unit tests for each scoring layer independently:
  - `_compute_base_score`: path patterns, entry points, category boost
  - `_compute_dimension_boost`: keyword matching per dimension, maintainability file-size curve, consolidated `max()` across dimensions
  - `_compute_fan_in`: mock source files with import statements, verify counts
  - `_compute_git_scores`: mock git output, verify churn and recency scoring
  - `_compute_previous_violations`: mock JSONL from previous run, verify counts
- Unit test: `prioritize_files` returns files sorted by total score descending
- Unit test: small project (≤50 files) returns all files (just reordered)
- Unit test: consolidated mode takes max dimension boost
- Unit test: graceful fallback when git unavailable (score 0, no error)
- Unit test: graceful fallback when no previous run (score 0)
- Integration test: verify FileQueue receives files in priority order

### Pool Budget
- Unit test: `pool_budget` flows from CLI flag to `AnalysisConfig`
- Unit test: `pool_budget` flows from `QUODEQ_POOL_BUDGET` env var
- Unit test: CLI flag takes precedence over env var
- Unit test: `SubagentPool.run()` respects custom `pool_budget` separately from `max_duration`
- Unit test: API route clamps `poolBudget` to 60-3600 range
- Unit test: `_should_respawn` uses pool_budget, not max_duration

### Incremental Analysis
- Unit test: fingerprint generation (git commit + file hashes + standards checksum)
- Unit test: change detection via git diff
- Unit test: change detection via hash comparison (no git)
- Unit test: dependency cascade — changed file's importers classified as "dependent"
- Unit test: unchanged file findings carried forward correctly
- Unit test: standards checksum change triggers full re-analysis
- Unit test: first run (no previous fingerprint) falls back to full analysis
- Unit test: merge of carried-forward + new findings with deduplication
- Integration test: 100 files, change 5, verify only ~5-10 analyzed

---

## Risks

| Risk | Mitigation |
|------|------------|
| Keyword-based dimension boost misclassifies files | Keywords are conservative (common patterns); config is tunable; worst case = same as current alphabetical order |
| Import fan-in grep is slow on huge repos | Single pass, pattern matching only; timeout after 10 seconds and skip (score 0). Estimated <3s for 4K files |
| Git not available (archive, shallow clone) | Graceful fallback: layer scores 0, no error |
| File size measurement adds latency | Only `os.path.getsize()` — fast, no file reads |
| Pool budget too low causes incomplete evaluation | Minimum 60 seconds enforced; UI shows warning below 5 minutes |
| Previous violations from stale run mislead priority | Only use findings from the most recent previous run; `_pre_filter_gone` already drops findings for deleted files |
| Import patterns miss language-specific syntax | Patterns are extensible via config; miss = score 0 for that file (falls back to other layers) |
| Stale cache: carried-forward findings reference code that semantically changed but file hash is same | Extremely rare (same hash = same content). Not possible with content-based hashing |
| Dependency cascade misses indirect effects | Limited to 1-level deep intentionally; transitive cascade is unbounded. Worst case: a finding is stale until next full evaluation |
| First incremental run slow due to fingerprint generation | File hashing is fast (~1s for 4K files). Git commit is instant. One-time cost |
| User expects incremental to catch everything | UI should clearly label "incremental" vs "full" scan, with option to force full re-evaluation |
