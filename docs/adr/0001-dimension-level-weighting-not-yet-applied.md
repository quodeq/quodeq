# ADR 0001: Dimension-level weighting is not yet applied

## Status

Partially superseded, see status update below. Originally: Accepted (documents existing behavior). Bootstraps `docs/adr/`.

## Context

`src/quodeq/data/config/dimensions.json` declares a `weight` field on every
entry in `applies`, with values that look deliberately tuned:

| Dimension       | Weight |
| --------------- | ------ |
| security        | 1.2    |
| reliability     | 1.0    |
| maintainability | 1.0    |
| performance     | 0.8    |
| usability       | 0.6    |
| flexibility     | 0.6    |
| clean-architecture | 1.0 |
| domain-driven-design | 1.0 |

The `iso_25010` and `source` fields point at ISO/IEC 25010:2023 as the
underlying model. `dimensions_schema.json` lists `weight` as required and
`tests/engine/test_universal_dimensions.py::test_all_dimensions_have_weight`
enforces it. The weight is also read by Python:

* `services/_standards_io.py::build_builtin_meta` reads `dim["weight"]`
  into `StandardMeta.weight`.
* `services/_standards_io.py::get_builtin_weight` is called by
  `services/_standards_queries.py::get_standard` to populate
  `StandardDetail.weight`.
* `core/types/standard.py` carries `weight: float` on both
  `StandardMeta` (line 20) and `StandardDetail` (line 36).
* The custom-standards CRUD path round-trips `weight` through
  `services/_standards_crud.py::duplicate` and the API.

So the field is present, validated, populated, and surfaced through the API.

### What it does NOT do

No scoring path multiplies any score by this weight. Both
dimension-to-run aggregators take a plain unweighted mean:

* Legacy: `data/fs/report_parser/_summary.py::summarize_dimensions`
  computes `sum(numeric_scores) / len(numeric_scores)`.
* SQL projection: `services/scoring/projector_scoring.py::compute_run_score`
  computes `sum(scored) / len(scored)`, and the mirror read path
  `data/sqlite/state_store.py::read_run_score_from_dim_scores` does the
  same.

The only weighted aggregation in the scoring stack is `weighted_overall`
in `core/scoring/overall.py`, which uses *principle-level*
`PrincipleScore.weight` (a multiplier label like `"High (x3)"`). That is a
separate concept from the `dimensions.json` weights.

### What the UI tells users

`src/quodeq/ui/src/features/help/components/HelpSections.jsx:252` reads:

> Each dimension is scored 0 to 10 with a letter grade. The project grade
> is a weighted average across enabled dimensions. See *Philosophy* for the
> full Q² formula.

This sentence is currently misleading: the project grade is a plain mean,
not a weighted average. The Philosophy section describes principle-level
scoring honestly and does not claim dimension-level weighting.

## Decision

Treat the per-dimension `weight` field as **aspirational, not applied**.

Keep the field, the schema requirement, the test, and the round-trip
through `StandardMeta` / `StandardDetail`. Document the state of play
inline with a top-level `_note` field in `dimensions.json` so the next
reader does not have to grep the codebase to figure out whether the
weights are live.

This avoids a breaking change to:

* the dimensions schema and validator,
* the custom-standards JSON contract (uploaded standards carry `weight`),
* the API shape consumed by the standards UI.

## Consequences

* The next person opening `dimensions.json` sees the note and knows the
  weights are not yet applied.
* Anyone planning to ship dimension-level weighting now has a checklist
  of touch points (see below) and a heads-up that grades will shift.
* The misleading help-copy sentence stays in place for now, since fixing
  it commits us to either landing weighting soon or removing the field.
  It is called out as a follow-up in the PR that introduces this ADR.

## Implementing weighted aggregation later

A future "apply dimension weights" PR would need to touch:

1. `data/fs/report_parser/_summary.py::summarize_dimensions`. The
   function currently does not receive weights. Either pass a weight
   lookup from the caller, or look up weights via the standards service.
2. `services/scoring/projector_scoring.py::compute_run_score` and the
   mirror reader `data/sqlite/state_store.py::read_run_score_from_dim_scores`.
   Both currently compute a plain mean over the `dim_scores` projection.
   Decide whether the weight lives in the SQL projection (denormalised
   into the dim row) or is joined in at read time.
3. The parity logger in PR2 of the live-grades work needs to be re-run
   after the change, because legacy vs SQL parity is currently exact
   *only because* both paths ignore weights identically. Once weights
   are applied, both paths must agree on the same weight source and the
   same formula.
4. `CHANGELOG.md`: document that project-level grades will shift for
   evaluations that mix high-weight and low-weight dimensions. Existing
   stored run scores in `evaluation.db` are a frozen projection of the
   old formula and can stay as is, but the next scoring run will produce
   different values for the same findings.
5. `src/quodeq/ui/src/features/help/components/HelpSections.jsx:252` is
   already correct text for the post-change world; no edit needed.
6. The Philosophy section may want a short mention of the dimension
   weight table so the help copy is no longer the only place the user
   encounters the concept.

## Alternatives considered

* **Delete the field**. Tempting, but the values look deliberate and the
  field is part of the on-disk schema for custom standards. Deleting
  would be a breaking change for users who have uploaded standards with
  `weight` set.
* **Rename to `weight_planned`**. Same breaking-change problem, and it
  fragments the `StandardMeta.weight` round-trip path.
* **Apply the weights now**. Out of scope for a docs/cleanup pass, and
  would shift every grade quietly without a parity-logger sweep.

## References

* `src/quodeq/data/config/dimensions.json`
* `src/quodeq/analysis/plugins/schemas/dimensions_schema.json`
* `src/quodeq/services/_standards_io.py`
* `src/quodeq/services/scoring/projector_scoring.py`
* `src/quodeq/data/fs/report_parser/_summary.py`
* `src/quodeq/core/types/standard.py`
* `src/quodeq/ui/src/features/help/components/HelpSections.jsx`

## Status update (2026-06-10)

Superseded in part by the Grade Formula Editor
(`docs/superpowers/specs/2026-06-10-grade-formula-editor-design.md`).
Dimension weights are now applied at runtime when the user enables the
"apply dimension weights" switch in Settings > Grade formula
(`ScoringParams.dimension_weights_enabled`). The default remains OFF, so
out-of-the-box behavior is unchanged (plain unweighted mean). The
aggregation paths (`summarize_dimensions`, `compute_run_score`, and the
accumulated view) all share `dimension_weighted_average()` from
`core/scoring/params.py`. Per-dimension grades, in turn, are unified at
the read layer: for event-log runs `read_run_data` overlays the SQL grade
tables (rewritten on dismiss and on a grade-formula Apply via
`data/projection/grade_projector.recompute_grades`) onto the eval-time
`DimensionResult`s, so the run-detail, accumulated, trend, and project-card
surfaces read the same numbers by construction. They can still drift if a
new aggregate is computed off the eval-time JSON without threading the saved
params or bypassing `read_run_data` — the shared average and the SQL grade
overlay are what keep them aligned, not an inherent guarantee.
