# Live Rescore on Dismiss

**Date:** 2026-04-02
**Status:** Approved

## Problem

When a user dismisses or restores a finding, the UI continues showing the original run scores. Grades only update after a full re-evaluation. Users expect scores to reflect the current state of violations immediately.

## Solution

Add a stateful backend `/rescore` endpoint that recalculates scores from the stored run data minus dismissed findings. The frontend calls this on dashboard load and after each dismiss/restore action. All score displays update through existing state flow.

## Design Decisions

- **Single source of truth:** Scoring formula lives only in the Python backend. No JS port.
- **Stateful endpoint:** Backend loads violations and dismissed list itself. Frontend just sends `projectId` and optional `runId`.
- **No caching:** Rescore computation is cheap (sub-50ms on localhost). Compute on every request.
- **No report mutation:** Original run reports stay intact. Rescored data is transient, returned per-request.
- **No "adjusted" indicator:** Deferred to future follow-up.

## Architecture

### Backend: `/rescore` Endpoint

**Route:** `GET /api/rescore?project=<projectId>&run=<runId>`

`run` is optional; defaults to latest run.

**Response:** Same structure the dashboard already consumes — updated `dimensions[]` with rescored `overallScore`, `overallGrade`, `totals`, and `principles[].score/grade`, plus a `summary` object for the run level.

**Flow:**

1. Load the run's dimension results from the stored report
2. Filter out dismissed findings via `filter_dismissed_from_dimensions()`
3. For each dimension, rescore:
   - Count violation types per severity per principle
   - Run `_score_principle_numerical()` (or graded equivalent) with filtered counts
   - Aggregate principle scores into dimension overall via `weighted_overall()`
4. Aggregate dimension scores into run summary via `summarize_dimensions()`
5. Return the full rescored structure

### New Module: `core/scoring/rescore.py`

**Primary function:** `rescore_dimensions(dimensions, dismissed_keys)`

Takes a list of already-parsed dimension results and a set of dismissed keys. Returns the fully rescored structure.

**Reuses existing functions (no changes needed):**

- `violation_base()` — Stage 1: base score from weighted violations
- `compliance_lift()` — Stage 2: lift from compliance items
- `violation_ceiling()` — Stage 3: cap based on violation weight
- `severity_grade_floor()` — Stage 4: floor based on worst severity
- `weighted_overall()` — Dimension-level aggregation (weighted average of principle scores)
- `summarize_dimensions()` — Run-level aggregation (simple average of dimension scores)
- `score_to_grade_label()` — Numeric score to grade word

**New helper to extract:** `count_violation_types(violations)`

Takes a list of violation dicts `[{severity, req, reason, ...}]` and returns type counts `{critical: N, major: N, minor: N}` using the existing type-counting logic (unique types per severity, not raw counts). Currently this logic is buried in the analysis pipeline and needs to be extracted as a standalone function.

### Scoring Aggregation Reference

Each level uses a different calculation:

| Level | Input | Method |
|-------|-------|--------|
| **Principle** | Violations + compliance | 4-stage formula (base, lift, ceiling, floor) |
| **Dimension** | Principle scores | Weighted average (principles have weight multipliers: x1, x2, x3) |
| **Run** | Dimension scores | Simple arithmetic average (all dimensions equal) |

### Frontend Integration

**When rescore is called:**

1. **On dashboard load** — after fetching dashboard data, call `/rescore`. Replace dimension scores in state with rescored values.
2. **After dismiss/restore** — chain rescore after the existing dashboard refresh. Debounce at 300ms for rapid-fire actions.

**Flow:**

```
User dismisses finding
  -> Card removed from UI (optimistic)
  -> POST /findings/dismiss
  -> GET /rescore?project=X
  -> Response updates dashboard state
  -> All score components re-render with new grades
```

**Components that update automatically (read from dashboard state):**

- `RunOverviewPanel` — ScoreCircle (run-level summary)
- `DimensionCard` — per-dimension score + grade chip
- `PrincipleAccordion` — per-principle scores
- `ExplorerPage` — dimension header scores
- `EvalPrincipleDetailPage` — principle header score

No new components or state management needed.

## Edge Cases

- **No dismissed findings:** Rescore returns original scores unchanged (filtering empty set is a no-op).
- **All violations dismissed in a principle:** Formula handles naturally — zero violations yields max score, limited by compliance lift. Grade becomes "Exemplary" if compliance exists.
- **Rescore endpoint fails:** UI keeps showing last known scores. Original dashboard data is already loaded as fallback.
- **Rapid dismiss/restore:** Debounced at 300ms. Each rescore reads current dismissed list from disk, so always produces correct result.
- **Scoring mode (numerical vs graded):** Backend knows each dimension's mode and calls the appropriate scoring path.
- **Historical runs:** Endpoint accepts optional `run` parameter. Dismissed findings are project-level, so historical scores also reflect current dismissals.

## Out of Scope

- No frontend scoring formula (backend is single source of truth)
- No cache layer (rescore is cheap enough per-request)
- No mutation of stored report files
- No "adjusted" indicator on rescored values
- No new UI components
- No changes to the existing analysis/evaluation pipeline
