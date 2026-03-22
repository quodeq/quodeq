# File Prioritization & Configurable Pool Budget

**Date:** 2026-03-22
**Status:** Draft

## Problem

For large projects (4K+ files), agents hit their time/turn budget before reading all files. Currently files are fed in alphabetical order — config files in `a/` get analyzed before critical source files in `s/`. When budget runs out, important files may never be evaluated, reducing score quality.

Additionally, the pool budget (10 minutes) is hardcoded with no user control.

## Design

Two independent features, both affecting evaluation quality for large projects.

---

## Feature 1: Dimension-Aware File Prioritization

### Scoring Model

Each file gets a priority score (0-20) computed from local heuristics at manifest time. Two components:

**Base score (0-10)** — project-type-aware, same for all dimensions:
- **Path pattern** (0-5): `src/`, `lib/`, `app/`, `core/` → 5; `pkg/`, `internal/` → 4; `test/`, `tests/` → 1; `docs/`, `scripts/` → 0
- **Entry point pattern** (0-3): files matching `main.*`, `app.*`, `index.*`, `routes.*`, `server.*` → 3
- **Category boost** (0-2): discipline-detected category (backend, mobile, frontend) boosts files matching category-specific patterns (e.g., `controller`, `service` for backend; `activity`, `fragment` for mobile)

**Dimension boost (0-5)** — varies per dimension being evaluated:
- `security`: files matching auth/crypto/route/handler/validation patterns → +5
- `reliability`: files matching error/retry/timeout/database/migration patterns → +5
- `maintainability`: boost by file size (largest files first, computed in code)
- `performance`: files matching cache/query/pool/batch/stream patterns → +5
- `flexibility`: files matching config/plugin/adapter/factory patterns → +5
- `usability`: files matching accessibility/i18n/form/input patterns → +5

**Consolidated mode**: `dimension_boost = max(boost across all selected dimensions)`.

**Small projects (≤50 files)**: all files are analyzed regardless; ordering still applied but doesn't affect coverage.

### Config Data File

Scoring rules in `src/quodeq/data/config/file_priority.json`. Keyword lists and path boosts are tunable without code changes. The `maintainability` dimension uses file size (computed at scoring time) rather than keywords.

### Integration Point

**`src/quodeq/analysis/subagents/runner.py`** — new function `prioritize_files()`:
- Called in `_list_source_files` before returning the file list
- Also called in `process_consolidated_dimensions` for the consolidated path
- Loads config (cached via `lru_cache`), scores each file, returns sorted descending
- Signature: `prioritize_files(files: list[str], src: Path, dimension: str | list[str], category: str | None) -> list[str]`

### Files Changed

**New files:**
- `src/quodeq/data/config/file_priority.json` — scoring rules
- `src/quodeq/analysis/subagents/priority.py` — scoring logic (new module, keeps runner.py focused)

**Modified files:**
- `src/quodeq/analysis/subagents/runner.py` — call `prioritize_files()` in `_list_source_files` and `process_consolidated_dimensions`

**Unchanged:**
- `FileQueue`, `SubagentPool`, prompt templates, MCP server, evidence parser — unaffected. The file list is just reordered before being fed to the queue.

### Cost

Zero extra tokens. Sorting runs in pure Python at prescan time before any AI sessions start. A few milliseconds of CPU for scoring.

---

## Feature 2: Configurable Pool Budget

### Current State

- `_DEFAULT_POOL_BUDGET = 600` (10 min) hardcoded in `pool.py`
- Per-agent duration (`--max-duration`, default 30 min) is CLI-configurable but separate
- Pool budget is not configurable from CLI, API, or web UI

### New Behavior

- **CLI flag**: `--pool-budget <seconds>` (default 600, range 60-3600)
- **Env var**: `QUODEQ_POOL_BUDGET`
- **`AnalysisOptions`**: new field `pool_budget: int | None = None`
- **`AnalysisConfig`**: new field `pool_budget: int = 600`
- **`SubagentPool.run()`**: use `config.pool_budget` instead of `_DEFAULT_POOL_BUDGET`
- **API route**: accept `poolBudget` from evaluation payload (seconds, clamped 60-3600)
- **`EvaluationOptions`**: new field `pool_budget: int = 600`
- **`_build_evaluate_cmd`**: pass `--pool-budget` when non-default
- **Web settings**: "Analysis time limit" number input (minutes), range 1-60, default 10. Stored in localStorage as `cc-pool-budget` (in seconds). Sent as `poolBudget` in API payload.

### Files Changed

- `src/quodeq/analysis/subprocess.py` — add `pool_budget` to `AnalysisConfig`
- `src/quodeq/analysis/subagents/pool.py` — use `config.pool_budget` in `run()`
- `src/quodeq/analysis/runner.py` — add `pool_budget` to `AnalysisOptions`, wire to `AnalysisConfig`
- `src/quodeq/cli_parser.py` — add `--pool-budget` flag
- `src/quodeq/cli.py` — wire flag + env var
- `src/quodeq/services/base.py` — add `pool_budget` to `EvaluationOptions`
- `src/quodeq/services/evaluation_mixin.py` — pass `--pool-budget` in `_build_evaluate_cmd`
- `src/quodeq/api/routes.py` — accept `poolBudget` from payload
- `src/quodeq/ui/src/features/settings/components/SettingsPage.jsx` — add time limit input
- `src/quodeq/ui/src/features/evaluation/hooks/useEvaluation.js` — send `poolBudget` in payload

---

## Testing

### File Prioritization
- Unit tests for scoring function: base score, dimension boost, category boost, consolidated max
- Unit test: small project (≤50 files) returns all files (just reordered)
- Unit test: file size boost for maintainability
- Integration test: verify FileQueue receives files in priority order

### Pool Budget
- Unit test: `pool_budget` flows from CLI to `AnalysisConfig`
- Unit test: `SubagentPool.run()` respects custom `pool_budget`
- Unit test: API route clamps `poolBudget` to 60-3600 range

---

## Risks

| Risk | Mitigation |
|------|------------|
| Keyword-based dimension boost misclassifies files | Keywords are conservative (common patterns); config is tunable; worst case = same as current alphabetical order |
| File size measurement adds latency for huge repos | Only `os.path.getsize()` — fast, no file reads. Cache if needed |
| Pool budget too low causes incomplete evaluation | Minimum 60 seconds enforced; UI shows warning below 5 minutes |
