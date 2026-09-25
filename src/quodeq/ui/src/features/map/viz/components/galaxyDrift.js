/**
 * Idle star drift, shared verbatim by useGalaxyCamera and
 * useGalaxyFolderCamera. Unlike the per-view lerp rates and view margins
 * (which stay in their own hooks because the two views chase their targets
 * at different speeds), drift is identical on both, so it lives here once
 * instead of as two copies.
 *
 * Sine on x, cosine on y; the speeds and phases are deliberately unequal so
 * the two axes never sync into a straight-line wobble. One amplitude
 * (world units) serves both axes.
 */
export const DRIFT = Object.freeze({
  speedX: 0.015,
  speedY: 0.012,
  phaseX: 1.1,
  phaseY: 0.8,
  amplitude: 2,
});
