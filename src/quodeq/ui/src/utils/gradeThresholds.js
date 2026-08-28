/**
 * Single client-side source of truth for score → grade-label boundaries.
 * Seeded with the backend Q2 defaults; App.jsx overwrites them at boot from
 * GET /api/grade-formula so every surface agrees with the server formula.
 *
 * State lives inside store instances (createGradeThresholdsStore) so tests
 * can grade against an isolated table; the module keeps one default store
 * and the historical named exports delegate to it, so the app still shares
 * a single table process-wide.
 */
const DEFAULT_THRESHOLDS = Object.freeze([
  Object.freeze([9, 'Exemplary']),
  Object.freeze([7, 'Good']),
  Object.freeze([5, 'Adequate']),
  Object.freeze([3, 'Poor']),
]);

/**
 * Build an independent thresholds store: get/set/reset plus a
 * scoreToGradeLabel bound to this instance's table.
 */
export function createGradeThresholdsStore() {
  let thresholds = DEFAULT_THRESHOLDS;
  return {
    // Returns the threshold table by reference. It is frozen so callers
    // (all read-only today) cannot mutate grading through the reference.
    get() {
      return thresholds;
    },
    set(next) {
      if (!Array.isArray(next) || next.length === 0) return;
      const clean = next
        .filter((e) => Array.isArray(e) && typeof e[0] === 'number' && typeof e[1] === 'string')
        .map((e) => Object.freeze([e[0], e[1]]));
      if (clean.length === next.length && clean.length > 0) thresholds = Object.freeze(clean);
    },
    reset() {
      thresholds = DEFAULT_THRESHOLDS;
    },
    /** Numeric or "9.1/10"-style input → label string, or null for bad input. */
    scoreToGradeLabel(score) {
      if (score === null || score === undefined || score === '') return null;
      const n = typeof score === 'number' ? score : parseFloat(score);
      if (Number.isNaN(n)) return null;
      for (const [threshold, label] of thresholds) {
        if (n >= threshold) return label;
      }
      return 'Critical';
    },
  };
}

/** The app-wide table every production import shares. */
export const defaultGradeThresholdsStore = createGradeThresholdsStore();

export function getGradeThresholds() {
  return defaultGradeThresholdsStore.get();
}

export function setGradeThresholds(next) {
  defaultGradeThresholdsStore.set(next);
}

export function resetGradeThresholds() {
  defaultGradeThresholdsStore.reset();
}

/** Numeric or "9.1/10"-style input → label string, or null for bad input. */
export function scoreToGradeLabel(score) {
  return defaultGradeThresholdsStore.scoreToGradeLabel(score);
}
