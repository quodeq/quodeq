/**
 * galaxyEasing.js — the easing curves the two galaxy cameras run.
 *
 * Both useGalaxyCamera and galaxyFolderCamera interpolate a camera from
 * where it is to where it should be, and both spelled the same standard
 * curves out inline as bare coefficients. Named once here, the call sites
 * read as the curve they are (`easeInOutCubic(anim.t)`) instead of as an
 * arithmetic puzzle, and a coefficient can only be wrong in one place.
 *
 * Every function takes and returns a 0..1 progress value, and none of them
 * clamps: callers already keep `t` in range.
 */

// The in-out curves are the standard easings: `SCALE * t^POWER` for the
// first half, the same curve point-mirrored through (MIDPOINT, MIDPOINT)
// for the second, so the two halves meet with a continuous slope.
const MIDPOINT = 0.5;
const CUBIC_POWER = 3;
const CUBIC_IN_SCALE = 4;
const QUAD_POWER = 2;
const QUAD_IN_SCALE = 2;
// The mirrored half is written as `1 - (MIRROR_SLOPE * t + 2)^POWER / 2`:
// the slope folds the second half back onto the first.
const MIRROR_SLOPE = -2;
const MIRROR_OFFSET = 2;
const MIRROR_HALVING = 2;

// The lag curve: a fractional power holds the value back early on, and
// smoothstep (3t^2 - 2t^3, written in Horner form) takes the corners off.
const LAG_POWER = 0.7;
const SMOOTHSTEP_A = 3;
const SMOOTHSTEP_B = 2;

/**
 * Slow start, fast middle, slow end, on a cubic. The main camera transition
 * curve: it spends most of its time near the endpoints, so the move reads as
 * deliberate rather than linear.
 *
 * @param {number} t Progress, 0..1.
 * @returns {number} Eased progress, 0..1.
 */
export function easeInOutCubic(t) {
  return t < MIDPOINT
    ? CUBIC_IN_SCALE * t * t * t
    : 1 - Math.pow(MIRROR_SLOPE * t + MIRROR_OFFSET, CUBIC_POWER) / MIRROR_HALVING;
}

/**
 * The same shape on a quadratic: gentler at both ends than the cubic, used
 * for the first half of a fly-in where the camera is still gathering speed.
 *
 * @param {number} t Progress, 0..1.
 * @returns {number} Eased progress, 0..1.
 */
export function easeInOutQuad(t) {
  return t < MIDPOINT
    ? QUAD_IN_SCALE * t * t
    : 1 - Math.pow(MIRROR_SLOPE * t + MIRROR_OFFSET, QUAD_POWER) / MIRROR_HALVING;
}

/**
 * Fast start, long settle. Used where a scene has just been swapped in and
 * should arrive immediately and then come to rest.
 *
 * @param {number} t Progress, 0..1.
 * @returns {number} Eased progress, 0..1.
 */
export function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, CUBIC_POWER);
}

/**
 * The gentler fast-start curve, for the bloom-in after a fly-out swap.
 *
 * @param {number} t Progress, 0..1.
 * @returns {number} Eased progress, 0..1.
 */
export function easeOutQuad(t) {
  return 1 - (1 - t) * (1 - t);
}

/**
 * The trailing curve: the same move, held back early and smoothed, so the
 * axis it drives starts after the leading axis and still lands with it.
 * Position lags zoom when flying in, zoom lags position when flying out.
 *
 * @param {number} t Progress, 0..1.
 * @returns {number} Eased progress, 0..1.
 */
export function easeLagged(t) {
  const lag = Math.pow(t, LAG_POWER);
  return lag * lag * (SMOOTHSTEP_A - SMOOTHSTEP_B * lag);
}
