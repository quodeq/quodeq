// Grade-formula draft business rules, applied by useGradeFormula's update()
// funnel before a patch is merged into the draft.
//
// Server-side (analysis/params.py) already enforces the real invariants and
// 400s an invalid save -- this is UI-only DRY, not a port of validate_params:
// it just keeps the two floor sliders from visibly fighting each other while
// the user drags (each slider used to clamp itself inline; centralizing it
// here means every caller of update() gets the same behaviour for free).

/**
 * Keep `floorMinor >= floorMajor` when a patch touches either floor.
 *
 * NO-OP on any patch that doesn't set `floorMinor` or `floorMajor` (e.g. a
 * `gradeThresholds` patch from the boundaries divider) -- returns the patch
 * unchanged. `draft` is the PRE-patch state; the other floor's current
 * value is what an incoming edit clamps against, matching the sliders'
 * previous inline behaviour.
 */
export function clampFloors(draft, patch) {
  if (!draft || !patch) return patch;
  if (!('floorMinor' in patch) && !('floorMajor' in patch)) return patch;

  const next = { ...patch };
  if ('floorMinor' in next) {
    next.floorMinor = Math.max(next.floorMinor, draft.floorMajor);
  }
  if ('floorMajor' in next) {
    next.floorMajor = Math.min(next.floorMajor, draft.floorMinor);
  }
  return next;
}
