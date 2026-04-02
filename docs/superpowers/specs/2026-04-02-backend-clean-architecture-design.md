# Backend Clean Architecture Refactoring

**Date:** 2026-04-02
**Status:** Approved
**Scope:** Backend Python code only (sub-project A). Frontend cleanup is a separate spec.

## Problem

Recent feature additions have increased complexity: god files with 19+ imports, a 248-line function, duplicated code across modules, and three dead shim directories left over from a previous migration. The architecture is sound but needs cleanup to stay maintainable.

## Solution

Four phased PRs, each independently reviewable and revertable. Pure refactoring — no behavior changes. All 687 tests must pass after each phase.

## Design Decisions

- **Phased by risk:** Dead code first (lowest risk), boundary enforcement last (highest value but informed by prior cleanup).
- **No new features:** This is strictly a refactoring effort. No behavior changes.
- **Preserve test coverage:** Move tests alongside code. No test deletions.
- **One PR per phase:** Each phase produces a working, tested codebase.

---

## Phase 1: Dead Code Removal (PR 1)

Remove legacy re-export shim directories and top-level shim files left from the Phase 6 migration (commit afee10a).

### Directories to delete

| Directory | Lines | Shims for | Imports to fix |
|-----------|-------|-----------|----------------|
| `src/quodeq/adapters/` | ~150 | `data/` | 3 (tooling_mixin.py, violations.py, _file_lock.py) |
| `src/quodeq/ports/` | ~50 | `data/ports/` | 2 (self-referential) |
| `src/quodeq/provider/` | ~71 | `services/` | 8 (api/, __init__.py, tests) |

### Files to delete

| File | Shim for |
|------|----------|
| `src/quodeq/action_api.py` | `api/app.py` |
| `src/quodeq/action_api_routes.py` | `api/routes.py` |
| `src/quodeq/action_api_helpers.py` | `api/helpers.py` |
| `src/quodeq/action_api_zip.py` | `api/zip.py` |

### Process

For each shim: find all importers via grep, redirect imports to canonical location, delete the shim. Run full test suite after each directory removal.

### Net result

~300 lines removed, 3 directories eliminated, cleaner import paths.

---

## Phase 2: Function Extraction & Duplication Consolidation (PR 2)

### Target 1: Break apart `services/standards.py:_count_principles_and_requirements()` (248 lines)

Extract into focused functions, each under 50 lines:
- `_count_principles(standard)` — count principles per standard
- `_count_requirements(principle)` — count requirements per principle
- `_aggregate_standard_counts(standards)` — roll up totals
- `_format_count_summary(counts)` — format for display

### Target 2: Consolidate `_compute_tallies` duplication

Currently duplicated in `core/scoring/engine.py:176` and `services/rescore.py`. Move to `core/scoring/internals.py` (where the tally functions already live). Both consumers import from there.

### Target 3: Consolidate `_recount_totals` duplication

Currently in `services/rescore.py` and `services/dismissed.py`. Keep in `services/dismissed.py` (the original), import from there in `rescore.py`.

### Target 4: Consolidate standard loaders

`engine/standards.py` duplicates loading functions from `core/standards/loader.py` (`load_dimension`, `load_asvs_l1`, `load_cisq`). Make `engine/standards.py` import from `core/standards/loader.py`. If `engine/standards.py` adds no orchestration value beyond re-exporting, delete it and redirect its importers.

### Net result

~300 lines of duplication eliminated. No function over 50 lines in touched files.

---

## Phase 3: God File Decomposition (PR 3)

### Target 1: `services/filesystem.py` (282 lines, 19 imports)

The `FilesystemActionProvider` class implements the full `ActionProvider` protocol in one file. Split by responsibility:

| New file | Responsibility | Methods moved |
|----------|---------------|---------------|
| `services/_fs_projects.py` | Project CRUD | list_projects, delete_project, update_project_path, clone_to_local, get_project_info |
| `services/_fs_reports.py` | Report/dashboard reading | get_dashboard, get_accumulated, get_dimension_eval, get_violations |
| `services/_fs_evaluations.py` | Evaluation operations | start_evaluation, get_evaluation_status, cancel_evaluation |

`services/filesystem.py` becomes a thin facade: the `FilesystemActionProvider` class delegates to mixin classes or module-level functions from the new files. Import count drops from 19 to ~8.

### Target 2: `services/_filesystem_helpers.py` (262 lines, 16 functions)

Redistribute helpers to the modules they serve:
- Path/directory helpers → stay in `_filesystem_helpers.py` (trimmed to ~80 lines)
- Report parsing helpers → `_fs_reports.py`
- Project metadata helpers → `_fs_projects.py`

### Target 3: `services/accumulated.py` (268 lines, 12 functions)

Split:
- `services/accumulated.py` — public API (`compute_accumulated`, top-level orchestration)
- `services/_accumulated_helpers.py` — dimension bucketing, trend computation, score aggregation helpers

### Target 4: `services/violations_parsing.py` (300 lines, 12 functions)

Split:
- `services/violations_parsing.py` — main parsing entry point and public API
- `services/_violation_filters.py` — filtering, classification, and type-counting helpers

### Net result

No file over 200 lines in `services/`. Each module has one clear responsibility. Import counts under 12 per file.

---

## Phase 4: Layer Boundary Enforcement (PR 4)

### Import rules

```
core/          → may import: stdlib, core/ only
               → never imports: services/, api/, data/, engine/, analysis/

engine/        → may import: stdlib, core/
               → never imports: services/, api/, data/

data/          → may import: stdlib, core/
               → never imports: services/, api/, engine/, analysis/

services/      → may import: stdlib, core/, data/ (via services/ports.py boundary)
               → never imports: api/, engine/, analysis/

api/           → may import: stdlib, core/, services/
               → never imports: data/, engine/, analysis/

analysis/      → may import: stdlib, core/, engine/, data/, services/
               → never imports: api/

dashboard/     → may import: stdlib, services/, api/
               → never imports: core/, data/ directly
```

### File size guidelines (soft limits)

| Metric | Limit |
|--------|-------|
| File lines | 250 |
| Function lines | 50 |
| Imports per file | 15 |
| Functions per file | 12 |

### Deliverables

1. **`ARCHITECTURE.md`** at project root — documents layers, import rules, file size guidelines, and directory purpose
2. **Violation audit** — check all current imports against the rules, fix any violations found (should be few after Phases 1-3)
3. **`scripts/check_imports.py`** — simple lint script that validates layer import rules, can run in CI

### Net result

Architecture is documented, enforceable, and self-describing. New contributors know where code goes. CI catches violations.

---

## Out of Scope

- Frontend refactoring (separate spec: sub-project B)
- New features or behavior changes
- Test refactoring (tests move with their code but aren't restructured)
- CLI decomposition (`cli.py` — deferred to a future phase)
- Analysis layer cleanup (`analysis/runner.py`, `analysis/subprocess.py` — deferred)
