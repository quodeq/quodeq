// The alpha curves the galaxy draw pass applies as the camera zooms: what
// dims, what hands off to the next level of detail, and how fast. Kept apart
// from galaxyViewDraw.js so the drawing code reads as drawing and a tweak to
// a fade curve is a one-file change.
import { ZOOM_DIMENSION_LEVEL, ZOOM_PRINCIPLE_LEVEL } from '../core/galaxyTunables.js';
import { UNFOCUSED_CLUSTER_MIN_ALPHA } from './galaxyTuning.js';

// Zoom units past ZOOM_PRINCIPLE_LEVEL over which the selected principle's
// particles and label hand off to its violation orbs, which fade in over
// the same span.
export const PRINCIPLE_FADE_SPAN = 20;
// The other principles' labels get out of the way faster than that.
const SIBLING_LABEL_FADE_SPAN = 15;
// Zoom units over which an unfocused cluster dims, and the zoom at which
// that dimming starts.
const CLUSTER_DIM_SPAN = 2;
const CLUSTER_DIM_START_ZOOM = 1;
// Zoom units over which the selected star's own decorations fade out.
const SELECTED_DECOR_FADE_SPAN = 2;

/**
 * Alpha that is 1 at zoom `level` and drops by 1 every `span` of zoom past
 * it, never below 0.
 *
 * @param {number} camZ - the camera zoom.
 * @param {number} level - the zoom the fade starts at.
 * @param {number} span - the zoom distance of a full fade.
 * @returns {number}
 */
export function fadeOutFrom(camZ, level, span) {
  return Math.max(0, 1 - (camZ - level) / span);
}

/**
 * Dimming applied to stars outside the focused cluster, so the focused one
 * reads as the subject. Stars in the focused cluster (or every star when no
 * cluster is focused) stay at full alpha.
 *
 * @param {object} s - the star, carrying its cluster centre.
 * @param {object} cam - the current camera.
 * @param {object} nav - the navigation state, naming the focused cluster.
 * @returns {number} alpha multiplier in [UNFOCUSED_CLUSTER_MIN_ALPHA, 1].
 */
export function clusterDimming(s, cam, nav) {
  const inFocusedCluster = nav.clusterCx == null || (s._clusterCx === nav.clusterCx && s._clusterCy === nav.clusterCy);
  if (inFocusedCluster) return 1;
  return unfocusedClusterAlpha(cam.z);
}

/**
 * Alpha of anything drawn for a cluster other than the focused one: it fades
 * as the camera zooms in, down to UNFOCUSED_CLUSTER_MIN_ALPHA.
 *
 * @param {number} camZ - the camera zoom.
 * @returns {number}
 */
export function unfocusedClusterAlpha(camZ) {
  return Math.max(UNFOCUSED_CLUSTER_MIN_ALPHA, fadeOutFrom(camZ, CLUSTER_DIM_START_ZOOM, CLUSTER_DIM_SPAN));
}

/**
 * Alpha for the selected star's own decorations as the camera zooms into it:
 * they clear the view for the principles taking their place.
 *
 * @param {number} camZ - the camera zoom.
 * @returns {number} alpha in [0, 1].
 */
export function selectedZoomFade(camZ) {
  return fadeOutFrom(camZ, ZOOM_DIMENSION_LEVEL, SELECTED_DECOR_FADE_SPAN);
}

/**
 * Particle fade for one principle: the selected planet hands its particles
 * over to the large violation orbs as the camera zooms in; siblings keep
 * theirs at full strength.
 *
 * @param {number} camZ - the camera zoom.
 * @param {boolean} isSelected - whether this is the selected principle.
 * @returns {number} alpha in [0, 1].
 */
export function principleParticleFade(camZ, isSelected) {
  return isSelected ? fadeOutFrom(camZ, ZOOM_PRINCIPLE_LEVEL, PRINCIPLE_FADE_SPAN) : 1;
}

/**
 * Label alpha for one principle: the selected one fades as the camera zooms
 * into it, its siblings fade faster once any principle is selected, and every
 * label stays up while none is.
 *
 * @param {number} camZ - the camera zoom.
 * @param {boolean} isSelected - whether this is the selected principle.
 * @param {boolean} anySelected - whether any principle is selected.
 * @returns {number} alpha in [0, 1].
 */
export function principleLabelAlpha(camZ, isSelected, anySelected) {
  if (isSelected) return principleParticleFade(camZ, true);
  if (!anySelected) return 1;
  return fadeOutFrom(camZ, ZOOM_PRINCIPLE_LEVEL, SIBLING_LABEL_FADE_SPAN);
}
