# Grade Formula Editor — Design

**Date:** 2026-06-10
**Status:** Approved (brainstorm with Victor, visual mockups validated)
**Feature:** A Settings screen where users tune the Q² grading formula parameters with sliders and switches, see a live before/after preview on real project data, and apply the custom formula as the installation-wide grading policy.

## Background

The Q² scoring formula (introduced v0.6.0, commit `b14b7985`, documented in `src/quodeq/core/scoring/README.md`) computes grades through four constraints:

1. **Violation base**: `10 / (1 + K · weighted_violations)`, K = 0.12
2. **Compliance lift**: `(compliance / (compliance + weighted_violations))^1.8`
3. **Violation ceiling**: `10 − log₂(1 + weighted_violations) · 0.5`
4. **Severity grade floor**: critical → 0.0, major → 3.0, minor → 5.0

Inputs: severity weights (critical 4.0, major 1.5, minor 0.25) and grade-label thresholds (9/7/5/3 → Exemplary/Good/Adequate/Poor, fallback Critical). All constants are hard-coded in `src/quodeq/core/scoring/_constants.py` and from-imported (hard copies) into `internals.py` and `_tallies.py`.

Key architectural facts the design builds on:

- **Grades are projections, not truth.** `events.jsonl` stores verdicts only (no scores). `evaluation.db` grade tables (`dimension_scores`, `principle_grades`) are rebuilt by `Projector.project(force_rebuild=True)` → `recompute_grades()` in ~5–50ms per run of pure arithmetic. The dismissal-rescore path proves post-hoc recompute works.
- **Overall and accumulated/trend grades are computed at read time**, never persisted (`read_run_score_from_dim_scores()`, `compute_accumulated()`).
- **Three call paths** consume the formula functions: CLI engine (`core/scoring/_principle.py`), dismissal rescore (`services/rescore.py`), projector scoring (`services/scoring/projector_scoring.py`).
- **Dimension weights exist but are dormant** (ADR 0001): `dimensions.json` declares weights (security 1.2, performance 0.8, ...) but both aggregation paths take a plain mean.
- **A label divergence exists**: `ui/src/features/dashboard/components/dimensionGradeLabel.js` recomputes gauge labels client-side with thresholds 9/8/7/6 (incl. a FAIR tier) while the backend uses 9/7/5/3. Map legend and formatters use backend thresholds.
- **Dormant anti-pattern**: `configure_penalties()` in `core/scoring/numerical.py` (global mutation, never called anywhere). Not a precedent to follow.

## Decisions (made during brainstorm)

| Decision | Choice |
|---|---|
| Purpose | Sandbox with live preview + explicit Apply that makes params the real grading policy |
| Scope | Global (one set of params per installation) |
| Tunable groups | Severity weights, curve constants, floors & grade boundaries, dimension weights |
| Preview | Real project, latest run, before vs after (per-dimension + overall) |
| History on Apply | Everything rescores (runs, trends, accumulated); no per-run formula versioning |
| Preview computation | Server-side read-only endpoint; single formula implementation in Python |
| Layout | Tabbed parameter groups + bottom preview strip (validated via mockups) |
| Dimensions tab | Master toggle + per-dimension weight sliders |
| Not tunable | Confidence/insufficient-evidence gate, graded-mode ladder, deduction tables |

## 1. Core: injectable `ScoringParams`

New frozen dataclass in `core/scoring/` (e.g. `params.py`):

```python
@dataclass(frozen=True, slots=True)
class ScoringParams:
    severity_weight: Mapping[str, float]      # critical 4.0, major 1.5, minor 0.25
    base_k: float                              # 0.12
    lift_compress: float                       # 1.8
    ceil_scale: float                          # 0.5
    floor_minor: float                         # 5.0
    floor_major: float                         # 3.0  (critical floor fixed at 0.0)
    grade_thresholds: tuple[tuple[float, str], ...]  # ((9,"Exemplary"),(7,"Good"),(5,"Adequate"),(3,"Poor"))
    dimension_weights_enabled: bool            # False
    dimension_weights: Mapping[str, float]     # from dimensions.json declarations

DEFAULT_PARAMS = ScoringParams(...)  # exactly the current Q² constants
```

- The six pure functions take `params: ScoringParams = DEFAULT_PARAMS` explicitly: `violation_base`, `compliance_lift`, `violation_ceiling`, `severity_grade_floor`, `score_to_grade_label`, `_weighted_sum`.
- Thread `params` through the three call paths: `_principle.py` / `engine.run_scoring`, `services/rescore.py`, `services/scoring/projector_scoring.py` (`compute_principle_grade`, `compute_dimension_score`), plus `grade_projector.recompute_grades()` and the read-time aggregators that call `score_to_grade_label` (`overall.py`, `state_store.read_run_score_from_dim_scores`, `services/scoring/__init__.py`, `accumulated.py`).
- Grade *labels* stay fixed (Exemplary/Good/Adequate/Poor/Critical); only their numeric boundaries are tunable.
- Dimension weights, when enabled, apply in both aggregation paths per the ADR 0001 checklist (`summarize_dimensions` in `data/fs/report_parser/_summary.py` and `compute_run_score`/`read_run_score_from_dim_scores`). ADR 0001 gets updated/superseded.
- Validation (in the params model or service layer): all values within the UI slider ranges, grade boundary values strictly decreasing in tuple order (e.g. 9 > 7 > 5 > 3) and each within (0, 10), floors in [0, 10] with `floor_minor >= floor_major`, weights positive.
- Cleanup: delete dormant `configure_penalties()` / `reset_penalty_caches()` (never called anywhere).

## 2. Persistence + API

- Custom params persist at `~/.quodeq/grade_formula.json`. Absent file = Q² defaults. (`~/.quodeq/index.db` is owned by `run_index.py` and is not touched.)
- New `services/grade_formula.py`: `load_params() -> ScoringParams` (defaults when absent/corrupt, with warning), `save_params()`, `reset_params()`, validation shared with the API layer.
- New route module `api/_grade_formula_routes.py`, registered in `routes_registry.py`:
  - `GET /api/grade-formula` → `{ current, defaults, isCustom }` (also serves the thresholds the UI needs for label rendering)
  - `PUT /api/grade-formula` → validate (400 on bad ranges/crossing boundaries), save, run the apply pipeline, return fresh scores summary
  - `DELETE /api/grade-formula` → reset to defaults, same apply pipeline
  - `POST /api/grade-formula/preview` → body `{ params, project }`; recomputes the project's latest run **in memory, read-only** (never writes `evaluation.db`), returns `{ before, after }` with per-dimension `{ score, grade }` + overall. Reads findings via the existing SQLite read path and calls `compute_principle_grade(..., params=...)` without the state-store write step.

## 3. Apply pipeline

On `PUT`/`DELETE`:

1. Persist (or remove) `grade_formula.json`.
2. For every project/run that has an `events.jsonl`: `Projector.project(events_log, run_dir, force_rebuild=True)` with the new params (now params-aware), rebuilding `dimension_scores` + `principle_grades`. ~5–50ms per run; per-run locks already serialize against concurrent projection.
3. Flush the two LRU caches (`_SHARED_RUN_DIM_CACHE` in `services/dashboard.py`, accumulated cache in `services/accumulated.py`).
4. UI refetches scores; overall/accumulated/trend pick up new values automatically since they are read-time computations.

Edge cases:

- **Legacy runs without `events.jsonl`** (pre-event-log era) cannot be rescored; they keep stale grades via the JSON fallback path. Accepted and documented.
- **Evaluation in flight during Apply**: the run's CLI-written JSON may use old params, but the SQL projection (source of truth for modern runs) recomputes with current params on its next projection. The eval subprocess reads params at start; no mid-run re-read.
- Apply shows a confirmation dialog in the UI: applying rescores all runs and trends.

## 4. UI

### Entry + navigation

- Settings gains a "Grade formula" entry that `navPush`es a new full screen `GradeFormulaPage` (`features/settings/components/` or a sibling feature dir), registered in `ROUTE_RENDERERS` in `App.jsx`.

### Layout (validated via mockups, `.superpowers/brainstorm/46726-1781074336/content/layout-v3.html` + `boundaries.html`)

- **Header**: back to settings, screen title, project picker for the preview (default: last-viewed project, latest run).
- **Tabs**: SEVERITY · CURVE · BOUNDARIES · DIMENSIONS — one parameter group visible at a time.
  - **SEVERITY**: three sliders (critical/major/minor weights) with a plain-language hint line (e.g. "critical findings weigh 16x a minor one").
  - **CURVE**: compact SVG plot (~220px wide) left of the three sliders (strictness K, lift compress, ceiling scale). Plot shows base curve, dashed ceiling curve, shaded lift zone, grade-boundary gridlines, and a marker for a real dimension from the previewed run. The plot is redrawn client-side from slider values — presentation only; all grade numbers come from the server preview. One-line legend under the plot.
  - **BOUNDARIES**: a segmented 0–10 bar (CRITICAL/POOR/ADEQUATE/GOOD/EXEMPLARY) with draggable dividers for the grade thresholds, plus two floor sliders (minor-only, major) and a fixed non-adjustable "critical: no floor" row. Segment colors come from the existing theme grade tokens, never hard-coded.
  - **DIMENSIONS**: master switch "apply dimension weights" + one weight slider per dimension, pre-filled from `dimensions.json` declarations. Sliders disabled while the switch is off.
- **Bottom preview strip** (persistent across tabs): left-aligned before→after gauges for OVERALL + the dimensions enabled in standards and present in the previewed run, including the INSUFFICIENT state. Below the gauges, on their own row: **APPLY** (primary, enabled when dirty, confirm dialog) and **RESET Q²**, with an unsaved-changes hint.
- A short note on the screen states that confidence/insufficient-evidence gating is not affected by these parameters.

### Behavior

- Draft params live in component state; dirty-tracking against the saved params from `GET /api/grade-formula`.
- Slider changes trigger a debounced (~250ms) `POST /api/grade-formula/preview`; responses update the strip. Sliders are styled native `<input type="range">` with the value displayed numerically (no free-text inputs).
- No evaluations yet → preview strip shows an empty-state hint and APPLY still works.

### Label unification

- `dimensionGradeLabel.js` (client-side 9/8/7/6 mapping with FAIR) is removed. Gauge cards, map legend (`galaxyCore.js` LEGEND_ITEMS), and `formatters.js` score constants derive labels/boundaries from the served thresholds (fetched once via `GET /api/grade-formula` or piggybacked on the scores payload). The FAIR tier disappears; all surfaces agree with the backend.
- Help/Philosophy text (`HelpSections.jsx`) is updated: the "weighted average" sentence becomes accurate once dimension weights can actually be enabled.

## 5. Out of scope

- Confidence / insufficient-evidence gate thresholds (statistical sample-size logic, not grading taste).
- Per-project parameter overrides (revisit if real demand appears).
- Legacy graded-mode ladder (Insufficient/Developing/Proficient/Exemplary) and numerical-mode deduction/drop tables.
- Formula versioning per run (Apply rescores everything; one policy at a time).
- SSE streaming of preview updates (HTTP request/response is sufficient).

## 6. Testing

- **Scoring tests**: introduce a params fixture; defaults = Q² so existing assertions stay green. Add cases exercising non-default params for each of the six functions.
- **Params model**: validation rules (ranges, boundary ordering, floor ordering, weight positivity).
- **Persistence**: round-trip load/save/reset; corrupt file falls back to defaults.
- **API**: GET/PUT/DELETE/preview contract tests; PUT with invalid params → 400; preview is read-only (evaluation.db untouched — assert file mtime/contents).
- **Parity**: preview result for a run == grades after Apply with the same params (the critical invariant).
- **Rebuild**: projector rebuild with custom params is idempotent; legacy runs without events.jsonl are skipped without error.
- **UI**: dirty tracking, debounce, label lookup uses served thresholds (no FAIR), dimension toggle enables/disables sliders.
- **Docs**: update `docs/ui-map.md` (Settings table + new screen in the catalog + flow), update/supersede ADR 0001, update `core/scoring/README.md` with the params layer.

## Implementation notes

- Follow existing patterns: frozen dataclass config (`dashboard/_config.py`), route registration (`routes_registry.py`), camelCase API mappers (`core/types/mappers.py`).
- No em-dashes in user-facing UI strings.
- The mockup files under `.superpowers/brainstorm/` are gitignored sketches; the layout description above is authoritative.
