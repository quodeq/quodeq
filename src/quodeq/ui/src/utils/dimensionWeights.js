/**
 * The server's per-dimension weights for the overall score (Settings >
 * Grade formula), so a score the client recomputes, the Overview's with
 * some standards hidden, weighs dimensions the way the server's does
 * (core/scoring/params.py dimension_weighted_average). Seeded with no
 * weights, a plain mean, which is also the shipped default (every weight
 * 1.0); synced from GET /api/grade-formula at boot and on every apply.
 */
import { roundOneDecimalLikeServer } from './rounding.js';

// Lowercase dimension id -> weight, or null for a plain mean (weights off).
let weights = null;

/**
 * Adopt a grade formula's weights, `current` from GET /api/grade-formula.
 * Weights switched off, or a formula without them, mean a plain mean.
 * @param {{dimensionWeightsEnabled?: boolean, dimensionWeights?: Object}|null|undefined} formula
 */
export function setDimensionWeights(formula) {
  const table = formula?.dimensionWeights;
  weights = formula?.dimensionWeightsEnabled && table && typeof table === 'object' ? { ...table } : null;
}

/** Back to a plain mean (tests). */
export function resetDimensionWeights() {
  weights = null;
}

/**
 * Weighted mean of [dimensionId, score] pairs, rounded like the server's.
 * Missing scores are skipped; a dimension without a weight weighs 1. null
 * when nothing is left.
 * @param {Array<[string, number|null]>} pairs
 * @returns {number|null}
 */
export function weightedMeanScore(pairs) {
  let total = 0;
  let weight = 0;
  for (const [dim, score] of pairs) {
    if (score == null) continue;
    const w = typeof weights?.[dim] === 'number' ? weights[dim] : 1;
    total += score * w;
    weight += w;
  }
  return weight > 0 ? roundOneDecimalLikeServer(total / weight) : null;
}
