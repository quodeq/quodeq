import { buildFolderScene } from './galaxyFolderScene.js';
import { CAMERA } from './galaxyTuning.js';
import { easeInOutQuad, easeOutCubic, easeOutQuad } from './galaxyEasing.js';
import { interpolateCamera } from './galaxyCameraLerp.js';

// A fly transition runs in two halves. `swapAt` is the point in the fly
// where the old scene is exchanged for the new one; before it the camera
// works on the old scene, after it on the new one. `bloomZoomRatio` is the
// zoom the new scene opens at, as a multiple of its own fit zoom, and the
// bloom fades in from `bloomAlphaMin` over `bloomAlphaSpan`.
const FLY_OUT = Object.freeze({
  swapAt: 0.4, shrinkFraction: 0.7, fadeFraction: 0.8,
  bloomZoomRatio: 6, bloomAlphaMin: 0.2, bloomAlphaSpan: 0.8,
});
const FLY_IN = Object.freeze({
  swapAt: 0.35, zoomRatio: 4, fadeFraction: 0.85,
  bloomZoomRatio: 0.3, bloomAlphaMin: 0.15, bloomAlphaSpan: 0.85,
});
// Fraction of the remaining distance the idle camera covers each frame.
const IDLE_LERP_FRACTION = 0.08;

// The scene exchange each fly performs exactly once, at its swapAt: drop the
// refs that belong to the outgoing scene, install the staged one, and reopen
// the camera centred at the bloom zoom.
function swapToStagedScene(fly, cam, refs, params, node, bloomZoomRatio) {
  const { W, H, saveNav } = params;
  fly.swapped = true;
  refs.zoomedFileRef.current = null;
  refs.navRef.current = { path: [...fly.newPath] };
  refs.sceneRef.current = refs.nextSceneRef.current;
  refs.sceneRef.current._node = node;
  refs.nextSceneRef.current = null;
  refs.frameCount.current = 0;
  cam.x = W / 2; cam.y = H / 2; cam.z = (fly._targetFz || 1) * bloomZoomRatio;
  saveNav();
}

// The half of a fly after the swap: the new scene opens from bloomZoomRatio x
// its fit zoom back down to the fit zoom, with the bloom fading in over it.
// Returns the bloom alpha for this frame.
function openBloom(cam, fly, cfg, ease) {
  const tFz = fly._targetFz || 1;
  const pe = ease((fly.t - cfg.swapAt) / (1 - cfg.swapAt));
  const openZ = tFz * cfg.bloomZoomRatio;
  cam.z = openZ + (tFz - openZ) * pe;
  return cfg.bloomAlphaMin + cfg.bloomAlphaSpan * pe;
}

/**
 * Fly-out (back navigation): shrink out of the current scene, then swap to
 * the parent scene atomically at `swapAt` and grow the bloom in. The swap
 * (clearing zoom/focus refs, installing the new scene, resetting the
 * camera) happens in one place so nothing can observe a half-swapped state.
 */
function advanceFlyOut(fly, cam, refs, params) {
  if (fly.t < FLY_OUT.swapAt) {
    const p = fly.t / FLY_OUT.swapAt;
    cam.z = fly.sz * (1 - p * FLY_OUT.shrinkFraction);
    return { sceneAlpha: 1 - p * FLY_OUT.fadeFraction, bloomAlpha: 0 };
  }
  if (!fly.swapped) {
    refs.focusedFolderRef.current = null;
    const parent = fly.newPath[fly.newPath.length - 1];
    swapToStagedScene(fly, cam, refs, params, parent, FLY_OUT.bloomZoomRatio);
  }
  return { sceneAlpha: 0, bloomAlpha: openBloom(cam, fly, FLY_OUT, easeOutQuad) };
}

/**
 * Fly-in (enter folder): zoom into the clicked star, then swap to its child
 * scene atomically at `swapAt` and shrink the bloom out. The swap happens in
 * one place, same as advanceFlyOut.
 */
function advanceFlyIn(fly, cam, refs, params) {
  if (fly.t < FLY_IN.swapAt) {
    const pe = easeInOutQuad(fly.t / FLY_IN.swapAt);
    cam.x = fly.sx + (fly.starX - fly.sx) * pe;
    cam.y = fly.sy + (fly.starY - fly.sy) * pe;
    cam.z = fly.sz + (fly.sz * FLY_IN.zoomRatio - fly.sz) * pe;
    return { sceneAlpha: 1 - pe * FLY_IN.fadeFraction, bloomAlpha: 0 };
  }
  if (!fly.swapped) {
    const target = fly.targetNode || fly.newPath[fly.newPath.length - 1];
    swapToStagedScene(fly, cam, refs, params, target, FLY_IN.bloomZoomRatio);
  }
  return { sceneAlpha: 0, bloomAlpha: openBloom(cam, fly, FLY_IN, easeOutCubic) };
}

/**
 * Advance the fly-into/fly-out transition state.
 * Mutates fly, cam, and various refs. Returns { sceneAlpha, bloomAlpha }.
 */
export function advanceFlyTransition(fly, cam, refs, params) {
  const { FLY_DURATION, getFitZoom } = params;
  fly.t = Math.min(1, fly.t + CAMERA.frameStepS / FLY_DURATION);
  if (!fly._targetFz) {
    fly._targetFz = getFitZoom(refs.nextSceneRef.current);
  }
  return fly.reverse
    ? advanceFlyOut(fly, cam, refs, params)
    : advanceFlyIn(fly, cam, refs, params);
}

/**
 * Advance camera state (non-fly mode). Returns nothing, mutates cam in place.
 */
export function advanceCamera(cam, refs, params) {
  const { TRANS, scene, computeFocusCamera, W, H } = params;
  const tg = computeFocusCamera();
  refs.frameCount.current++;

  const done = interpolateCamera(
    cam, tg, refs.animRef.current, refs.frameCount.current, TRANS, IDLE_LERP_FRACTION,
  );
  if (!done) return;

  refs.animRef.current = null;
  refs.prevNavRef.current = null;
  // Auto-enter focused folder after zoom completes
  const ff3 = refs.focusedFolderRef.current;
  if (!ff3 || !ff3.autoEnter || refs.flyRef.current) return;
  const curScene = refs.sceneRef.current || scene;
  const star = curScene.rootStars[ff3.starIdx];
  if (!star || !star.isFolder) return;
  refs.nextSceneRef.current = buildFolderScene(star._node, W, H);
  refs.nextSceneRef.current._node = star._node;
  refs.flyRef.current = {
    t: 0,
    starX: star.x, starY: star.y,
    starCol: star.col,
    dimStarIdx: ff3.starIdx,
    sx: cam.x, sy: cam.y, sz: cam.z,
    targetNode: star._node,
    newPath: [...refs.navRef.current.path, star._node],
    swapped: false,
  };
  refs.focusedFolderRef.current = null;
}
