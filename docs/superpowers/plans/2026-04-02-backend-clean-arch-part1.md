# Backend Clean Architecture — Part 1 (Phases 1-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dead code shims, consolidate duplicated functions, and decompose god files in `services/` and `core/` layers to enforce a 100-line-per-file limit.

**Architecture:** Four phased PRs. Each PR is independently reviewable and revertable. Pure refactoring — no behavior changes. All tests must pass after each task.

**Tech Stack:** Python 3.14, pytest, dataclasses

**Test command:** `/Users/marche000/Projects/vik/quodeq/.venv/bin/python -m pytest tests/ -x -q --tb=short`

---

## Phase 1 (PR 1): Dead Code Removal

### Task 1: Remove `ports/` shim directory

The `src/quodeq/ports/` directory contains re-export shims for `data/ports/`. It has **zero imports** in the codebase — completely unused.

**Files:**
- Delete: `src/quodeq/ports/__init__.py`
- Delete: `src/quodeq/ports/dimensions.py`
- Delete: `src/quodeq/ports/evaluations.py`

- [ ] **Step 1: Verify no imports exist**

Run: `grep -r "from quodeq\.ports" src/ tests/ --include="*.py" | grep -v "quodeq\.ports\." | grep -v "data\.ports" | grep -v "services\.ports"`
Expected: No output (zero matches)

- [ ] **Step 2: Delete the directory**

```bash
rm -rf src/quodeq/ports/
```

- [ ] **Step 3: Run tests**

Run: `/Users/marche000/Projects/vik/quodeq/.venv/bin/python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove unused ports/ shim directory"
```

---

### Task 2: Remove unused top-level shim files

`action_api_routes.py` and `action_api_zip.py` have zero imports. `action_api_helpers.py` doesn't exist.

**Files:**
- Delete: `src/quodeq/action_api_routes.py`
- Delete: `src/quodeq/action_api_zip.py`

- [ ] **Step 1: Verify no imports exist**

Run: `grep -r "from quodeq\.action_api_routes\|from quodeq\.action_api_zip\|import quodeq\.action_api_routes\|import quodeq\.action_api_zip" src/ tests/ --include="*.py"`
Expected: No output

- [ ] **Step 2: Delete the files**

```bash
rm src/quodeq/action_api_routes.py src/quodeq/action_api_zip.py
```

- [ ] **Step 3: Run tests**

Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove unused action_api_routes and action_api_zip shims"
```

---

### Task 3: Redirect `action_api.py` imports and delete shim

`action_api.py` is imported by 3 test files. Redirect them to `quodeq.api.app`.

**Files:**
- Modify: `tests/test_action_api_health.py:1`
- Modify: `tests/test_action_api.py:5`
- Modify: `tests/test_power_selector_backend.py:151,166`
- Delete: `src/quodeq/action_api.py`

- [ ] **Step 1: Find all imports**

Run: `grep -rn "from quodeq\.action_api import\|from quodeq\.action_api " src/ tests/ --include="*.py"`

- [ ] **Step 2: Redirect imports**

In each file found, replace:
```python
from quodeq.action_api import create_app
```
with:
```python
from quodeq.api.app import create_app
```

Also check for any other symbols imported from `action_api` (like `RateLimitStore`, `InMemoryRateLimitStore`, etc.) and redirect to `quodeq.api.app`.

- [ ] **Step 3: Delete the shim**

```bash
rm src/quodeq/action_api.py
```

- [ ] **Step 4: Run tests**

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: redirect action_api imports to api.app, remove shim"
```

---

### Task 4: Redirect `provider/` imports and remove shim files

The `provider/` directory contains a mix of real logic files and shim re-exports. The shim files are `__init__.py` and `filesystem.py`. The real logic files (base.py, jobs.py, etc.) are the canonical implementations still referenced by `api/` and tests.

**Important:** `provider/` has real logic files — do NOT delete the whole directory. Only redirect the shim re-exports in `__init__.py` and `filesystem.py`, then update imports that go through them.

**Files:**
- Modify: `src/quodeq/api/routes.py:12` — change `from quodeq.provider.base import ActionProvider` to `from quodeq.services.base import ActionProvider`
- Modify: `src/quodeq/api/app.py:21,44` — same redirect for `ActionProvider` and `FilesystemActionProvider`
- Modify: `src/quodeq/api/routes_evaluation.py:11,12,48` — redirect `ActionProvider`, `get_allowed_client_ids`, `EvaluationOptions`
- Modify: `src/quodeq/__init__.py:5` — redirect `ActionProvider`
- Modify: `src/quodeq/provider/__init__.py` — remove re-exports (keep file minimal or empty)
- Modify: `src/quodeq/provider/filesystem.py` — remove re-export shim (keep file minimal or empty)

- [ ] **Step 1: Find all provider imports**

Run: `grep -rn "from quodeq\.provider\." src/ tests/ --include="*.py" | head -30`

- [ ] **Step 2: Redirect api/ imports**

For each import from `quodeq.provider.base`, redirect to `quodeq.services.base`.
For `quodeq.provider.filesystem`, redirect to `quodeq.services.filesystem`.
For `quodeq.provider.tooling_mixin`, redirect to `quodeq.services.tooling_mixin`.
For `quodeq.provider.plugin_discovery`, redirect to `quodeq.services.plugin_discovery` (verify this exists in services, otherwise leave as-is).

- [ ] **Step 3: Redirect test imports**

Find and update all test files importing from `quodeq.provider.*` to use `quodeq.services.*` equivalents. If a module exists in `provider/` but not `services/`, the provider file IS the canonical location — leave it.

- [ ] **Step 4: Clean up shim files**

Replace `src/quodeq/provider/__init__.py` with:
```python
"""Legacy provider package — canonical implementations are in quodeq.services."""
```

Replace `src/quodeq/provider/filesystem.py` with:
```python
"""Legacy shim — use quodeq.services.filesystem instead."""
```

- [ ] **Step 5: Run tests**

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: redirect provider imports to services, clean up shims"
```

---

### Task 5: Redirect `adapters/` imports where canonical alternatives exist

The `adapters/` directory contains real implementations alongside shim re-exports. Some modules have canonical equivalents in `data/` — redirect those. Leave modules that ARE the canonical location.

**Files:**
- Modify: `src/quodeq/services/violations.py:9` — redirect `from quodeq.adapters.fs.report_parser` to `from quodeq.data.fs.report_parser`
- Modify: `src/quodeq/services/tooling_mixin.py:15` — same redirect
- Modify: `src/quodeq/analysis/subagents/_file_lock.py:2` — redirect `from quodeq.adapters._file_lock` to `from quodeq.data._file_lock` (verify target exists)
- Modify: test files importing from `quodeq.adapters.*` — redirect to `quodeq.data.*` equivalents

- [ ] **Step 1: Find all adapters imports**

Run: `grep -rn "from quodeq\.adapters" src/ tests/ --include="*.py"`

- [ ] **Step 2: For each import, check if a `data/` equivalent exists**

For example: `quodeq.adapters.fs.report_parser` → check if `quodeq.data.fs.report_parser` exports the same symbols.

- [ ] **Step 3: Redirect imports where data/ equivalent exists**

Update each import to use `quodeq.data.*` instead of `quodeq.adapters.*`.

- [ ] **Step 4: For adapters modules with NO data/ equivalent, leave as-is**

These are the canonical implementations. They'll be addressed in a future phase if needed.

- [ ] **Step 5: Run tests**

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: redirect adapters imports to data layer where equivalent exists"
```

---

## Phase 2 (PR 2): Duplication Consolidation

### Task 6: Consolidate `_compute_tallies`

Currently in `core/scoring/engine.py` (works with raw dicts, returns 3-tuple) and `services/rescore.py` (converts Findings to dicts, returns 2-tuple). Make rescore use the core version.

**Files:**
- Modify: `src/quodeq/services/rescore.py`
- Modify: `src/quodeq/core/scoring/engine.py` — export `_compute_tallies` as `compute_tallies` (public)

- [ ] **Step 1: Make `_compute_tallies` public in engine.py**

In `src/quodeq/core/scoring/engine.py`, rename `_compute_tallies` to `compute_tallies` (remove leading underscore). Update the one internal call site in `_build_principle_context`.

- [ ] **Step 2: Update rescore.py to use core version**

In `src/quodeq/services/rescore.py`, replace the local `_compute_tallies` with:
```python
from quodeq.core.scoring.engine import compute_tallies
```

Update the call site to convert Findings to dicts first (using the existing `_finding_to_dict`), call `compute_tallies`, and ignore the third return value (using_taxonomy) if not needed.

- [ ] **Step 3: Run tests**

Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: consolidate _compute_tallies into core/scoring/engine"
```

---

### Task 7: Consolidate `_recount_totals`

Currently in `services/rescore.py` (takes `compliance_count: int`) and `services/dismissed.py` (takes `old_totals: Totals | None`). Consolidate into `dismissed.py` with a flexible signature.

**Files:**
- Modify: `src/quodeq/services/dismissed.py` — make `_recount_totals` public as `recount_totals`
- Modify: `src/quodeq/services/rescore.py` — import from dismissed

- [ ] **Step 1: Update dismissed.py**

Rename `_recount_totals` to `recount_totals`. Update its signature to accept either form:
```python
def recount_totals(violations: list[Finding], compliance_count: int | None = None, old_totals: Totals | None = None) -> Totals:
    """Recompute totals from a filtered violations list."""
    cc = compliance_count if compliance_count is not None else (old_totals.compliance_count if old_totals else 0)
    critical = major = minor = unknown = 0
    for v in violations:
        sev = (v.severity or "").lower()
        if sev == "critical":
            critical += 1
        elif sev == "major":
            major += 1
        elif sev == "minor":
            minor += 1
        else:
            unknown += 1
    return Totals(
        violation_count=len(violations),
        compliance_count=cc,
        severity=SeverityTally(critical=critical, major=major, minor=minor, unknown=unknown),
    )
```

Update the internal call site in `filter_dismissed_from_dimensions` to use `recount_totals(filtered, old_totals=dim.totals)`.

- [ ] **Step 2: Update rescore.py**

Remove `_recount_totals` from rescore.py. Import from dismissed:
```python
from quodeq.services.dismissed import recount_totals
```

Update the call site to use `recount_totals(filtered_violations, compliance_count=compliance_count)`.

- [ ] **Step 3: Run tests**

Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: consolidate recount_totals into services/dismissed"
```

---

## Phase 3 (PR 3): Services Layer — God File Decomposition (100-line target)

### Task 8: Split `services/filesystem.py` (282 lines)

Split by responsibility into focused modules. The `FilesystemActionProvider` becomes a thin facade using mixins.

**Files:**
- Create: `src/quodeq/services/_fs_projects.py` — project CRUD methods
- Create: `src/quodeq/services/_fs_reports.py` — report/dashboard reading methods
- Modify: `src/quodeq/services/filesystem.py` — keep class definition, delegate to new modules

- [ ] **Step 1: Extract project methods to `_fs_projects.py`**

Create `src/quodeq/services/_fs_projects.py` with these methods as module-level functions:
- `build_project_list(reports_root, ...)` (from `_build_project_list`)
- `list_projects_impl(reports_dir, ...)` (from `list_projects`)
- `update_project_path_impl(reports_dir, project, new_path)` (from `update_project_path`)
- `delete_project_impl(reports_dir, project)` (from `delete_project`)
- `clone_to_local_impl(reports_dir, project, destination)` (from `clone_to_local`)
- `get_project_info_impl(reports_dir, project)` (from `get_project_info`)

Each function takes the same parameters as the original method (minus `self`) plus any instance state it needs (like `_compiled_dir`).

- [ ] **Step 2: Extract report methods to `_fs_reports.py`**

Create `src/quodeq/services/_fs_reports.py` with:
- `get_dashboard_impl(reports_dir, project, run)` (delegates to `build_dashboard`)
- `get_accumulated_impl(reports_dir, project, as_of)` (delegates to `compute_accumulated`)
- `get_dimension_eval_impl(reports_dir, project, run_id, dimension, compiled_dir)` (from `get_dimension_eval`)
- `get_violations_impl(reports_dir, project, run_id)` (from `get_violations`)

- [ ] **Step 3: Slim down `filesystem.py`**

`FilesystemActionProvider` keeps its class definition, `__init__`, cache methods, and delegates to the extracted functions:
```python
def list_projects(self, reports_dir):
    return list_projects_impl(reports_dir, self._cache, ...)

def get_dashboard(self, reports_dir, project, run):
    return get_dashboard_impl(reports_dir, project, run)
```

Target: filesystem.py under 100 lines.

- [ ] **Step 4: Run tests**

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: split filesystem.py into _fs_projects and _fs_reports"
```

---

### Task 9: Split `services/_filesystem_helpers.py` (262 lines, 16 functions)

Redistribute helpers to the modules they serve.

**Files:**
- Modify: `src/quodeq/services/_filesystem_helpers.py` — keep only path/directory utilities
- Modify: `src/quodeq/services/_fs_projects.py` — absorb project-related helpers
- Create: `src/quodeq/services/_fs_metadata.py` — repo info, discipline detection, language stats

- [ ] **Step 1: Move project-building helpers to `_fs_projects.py`**

Move these functions from `_filesystem_helpers.py` to `_fs_projects.py`:
- `_build_project_entry`
- `_find_best_parent`
- `_auto_detect_parents`
- `_max_projects_listed`
- `_extract_project_metadata`
- `_check_path_exists`

- [ ] **Step 2: Extract metadata helpers to `_fs_metadata.py`**

Create `src/quodeq/services/_fs_metadata.py` with:
- `_read_repo_info`
- `_read_accumulated_summary`
- `_read_language_stats`
- `_read_discipline_from_eval`
- `_find_discipline_in_run`
- `_infer_discipline`
- `_has_fingerprints`

- [ ] **Step 3: Keep dimension-related helpers in `_filesystem_helpers.py`**

Keep only:
- `_read_dimensions_from_file`
- `reset_dimensions_cache`
- `_list_available_dimensions_for_discipline`

Target: `_filesystem_helpers.py` under 60 lines.

- [ ] **Step 4: Update all imports across codebase**

Grep for all imports from `_filesystem_helpers` and redirect to the new locations.

- [ ] **Step 5: Run tests**

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: redistribute _filesystem_helpers into focused modules"
```

---

### Task 10: Split `services/accumulated.py` (268 lines, 12 functions)

Split into public API and internal helpers.

**Files:**
- Create: `src/quodeq/services/_accumulated_helpers.py` — dimension bucketing, trend computation, score aggregation
- Modify: `src/quodeq/services/accumulated.py` — keep public API only

- [ ] **Step 1: Extract helpers to `_accumulated_helpers.py`**

Create `src/quodeq/services/_accumulated_helpers.py` with:
- `_DimensionBuckets` dataclass
- `_classify_dimension`
- `_read_all_run_data`
- `_compute_accumulated_trends`
- `_aggregate_severity_counts`
- `numeric_average`
- `_compute_accumulated_scores`
- `_AccumulatedResult` dataclass
- `_build_accumulated_response`
- `_compute_result`

- [ ] **Step 2: Slim down `accumulated.py`**

Keep only:
- `AccumulatedCacheConfig` dataclass
- `create_accumulated_cache`
- `_acc_dim_cache_max`
- `_resolve_cache`
- `compute_accumulated` (public entry point, delegates to helpers)

Target: `accumulated.py` under 80 lines.

- [ ] **Step 3: Update imports**

Only internal imports within accumulated.py need updating (to import from `_accumulated_helpers`).

- [ ] **Step 4: Run tests**

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: extract accumulated helpers into _accumulated_helpers"
```

---

### Task 11: Split `services/violations_parsing.py` (300 lines, 12 functions)

Split by data source: JSONL parsing, evidence parsing, stream parsing.

**Files:**
- Create: `src/quodeq/services/_violations_jsonl.py` — JSONL-specific parsing
- Create: `src/quodeq/services/_violations_stream.py` — stream-specific parsing
- Modify: `src/quodeq/services/violations_parsing.py` — keep public API + evidence parsing

- [ ] **Step 1: Extract JSONL parsing to `_violations_jsonl.py`**

Move:
- `_build_finding_entry`
- `_parse_jsonl_findings`
- `_load_req_to_principle`
- `parse_violations_from_jsonl`
- `_ResponseOptions` dataclass
- `_build_violation_response`

- [ ] **Step 2: Extract stream parsing to `_violations_stream.py`**

Move:
- `_try_parse_text_line`
- `_parse_entries_from_texts`
- `_StreamAccumulator` dataclass
- `_parse_stream_line`
- `parse_violations_from_stream`

- [ ] **Step 3: Slim down `violations_parsing.py`**

Keep only:
- `_build_violation_from_principle`
- `_extract_violations_from_principles`
- `parse_violations_from_evidence`
- Re-export public functions from the new modules for backward compatibility

Target: Each file under 100 lines.

- [ ] **Step 4: Update imports across codebase**

Grep for imports from `violations_parsing` and verify they still work (re-exports should handle this).

- [ ] **Step 5: Run tests**

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: split violations_parsing by data source (jsonl, stream, evidence)"
```

---

### Task 12: Split `services/standards.py` (275 lines)

Split service class methods from utility functions.

**Files:**
- Create: `src/quodeq/services/_standards_io.py` — file I/O, import/export helpers
- Modify: `src/quodeq/services/standards.py` — keep StandardsService class, slim

- [ ] **Step 1: Identify what to extract**

Read the full file. The `StandardsService` class likely has methods for CRUD, import, export. Extract the import/export logic (which involves file I/O, validation, JSON parsing) into `_standards_io.py`.

- [ ] **Step 2: Extract I/O functions to `_standards_io.py`**

Move file reading, writing, import validation, and export serialization functions.

- [ ] **Step 3: Keep StandardsService in `standards.py`**

The service class keeps its interface but delegates heavy operations to `_standards_io`.

Target: Each file under 100 lines.

- [ ] **Step 4: Run tests**

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: extract standards I/O helpers into _standards_io"
```

---

## Phase 4 (PR 4): Core Layer — God File Decomposition (100-line target)

### Task 13: Split `core/scoring/internals.py` (299 lines, 16 functions)

Split into scoring formula functions and utility/constant definitions.

**Files:**
- Create: `src/quodeq/core/scoring/_constants.py` — severity weights, grade thresholds, scale tiers
- Create: `src/quodeq/core/scoring/_tallies.py` — type counting functions (tally_types_by_taxonomy, etc.)
- Modify: `src/quodeq/core/scoring/internals.py` — keep the 4-stage formula functions + re-exports

- [ ] **Step 1: Extract constants to `_constants.py`**

Move:
- `_SEVERITY_WEIGHT`
- `_BASE_K`, `_LIFT_COMPRESS`, `_CEIL_SCALE`
- `_SEVERITY_GRADE_FLOOR`
- `GRADE_LADDER`
- `_GRADE_THRESHOLDS`
- `SCALE_TIERS`, `SCALE_TIER_NAMES`
- `scale_multiplier` function

- [ ] **Step 2: Extract tally functions to `_tallies.py`**

Move:
- `evidence_has_taxonomy`
- `tally_types_by_taxonomy`
- `tally_types_by_reason`
- `tally_compliance_types_by_taxonomy`
- `tally_compliance_types_by_reason`
- `_weighted_sum`

- [ ] **Step 3: Slim down `internals.py`**

Keep the 4-stage formula:
- `violation_base`
- `compliance_lift`
- `violation_ceiling`
- `severity_grade_floor`
- `score_to_grade_label`
- `compliance_dampening`
- `drop_grade`
- `weight_as_multiplier`

Import constants and tallies from new modules. Add re-exports for backward compatibility:
```python
from quodeq.core.scoring._constants import *  # noqa: F401,F403
from quodeq.core.scoring._tallies import *  # noqa: F401,F403
```

Target: Each file under 100 lines.

- [ ] **Step 4: Run tests**

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: split scoring internals into constants, tallies, and formulas"
```

---

### Task 14: Split `core/scoring/engine.py` (271 lines, 11 functions)

Split into principle scoring and overall aggregation.

**Files:**
- Create: `src/quodeq/core/scoring/_principle.py` — `_PrincipleContext`, `_score_principle_numerical`, `_score_principle_graded`, `_build_principle_context`
- Modify: `src/quodeq/core/scoring/engine.py` — keep public API (`run_scoring`, `score_evidence`, `compute_tallies`)

- [ ] **Step 1: Extract principle scoring to `_principle.py`**

Move:
- `_PrincipleContext` dataclass
- `_extract_metrics`
- `_build_principle_context`
- `_score_principle_numerical`
- `_score_principle_graded`
- `_score_all_principles`

- [ ] **Step 2: Slim down `engine.py`**

Keep:
- `compute_tallies` (public, from Task 6)
- `run_scoring` (main entry point)
- `score_evidence` (convenience wrapper)

Import from `_principle.py`:
```python
from quodeq.core.scoring._principle import _score_all_principles
```

Target: `engine.py` under 80 lines.

- [ ] **Step 3: Run tests**

Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: extract principle scoring into _principle module"
```

---

### Task 15: Split `core/evidence/parser.py` (287 lines, 11 functions)

Split evidence parsing from ref resolution.

**Files:**
- Create: `src/quodeq/core/evidence/_refs.py` — ref resolution, CWE/CISQ lookup
- Modify: `src/quodeq/core/evidence/parser.py` — keep evidence parsing only

- [ ] **Step 1: Read the file to identify the split boundary**

Read `src/quodeq/core/evidence/parser.py` fully. Identify which functions handle ref resolution (CWE, CISQ, ASVS lookups) vs evidence parsing.

- [ ] **Step 2: Extract ref functions to `_refs.py`**

Move all ref-resolution functions (likely: `build_req_refs_lookup`, `resolve_llm_refs`, CWE/CISQ mapping functions).

- [ ] **Step 3: Slim down `parser.py`**

Keep evidence parsing functions. Import refs from new module.

Target: Each file under 100 lines.

- [ ] **Step 4: Run tests**

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: extract evidence ref resolution into _refs module"
```

---

### Task 16: Split `core/types/mappers.py` and `_mapper_entities.py`

`mappers.py` (193 lines) and `_mapper_entities.py` (200 lines) both exceed the limit.

**Files:**
- Modify: `src/quodeq/core/types/mappers.py` — slim to public API
- Modify: `src/quodeq/core/types/_mapper_entities.py` — split if needed
- Create: `src/quodeq/core/types/_mapper_violations.py` — violation-specific mapping (if needed to get under 100)

- [ ] **Step 1: Read both files to assess the split**

Read the full content of both files. Identify logical groupings of mapper functions.

- [ ] **Step 2: Split based on entity type**

Group mappers by what they map (violations, dimensions, principles, projects, etc.). Create focused files for the largest groups.

- [ ] **Step 3: Update imports**

The public API (`mappers.py`) re-exports everything for backward compatibility.

Target: Each file under 100 lines.

- [ ] **Step 4: Run tests**

Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: split type mappers by entity"
```

---

### Task 17: Run full test suite and verify file sizes

Final verification for Part 1.

- [ ] **Step 1: Run full test suite**

Run: `/Users/marche000/Projects/vik/quodeq/.venv/bin/python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass

- [ ] **Step 2: Verify file sizes in touched modules**

Run: `wc -l src/quodeq/services/*.py src/quodeq/core/scoring/*.py src/quodeq/core/evidence/*.py src/quodeq/core/types/mappers.py src/quodeq/core/types/_mapper_entities.py | sort -rn | head -20`
Expected: No file exceeds 100 lines

- [ ] **Step 3: Commit final PR state**

```bash
git add -A
git commit -m "refactor: verify all touched files under 100-line limit"
```
