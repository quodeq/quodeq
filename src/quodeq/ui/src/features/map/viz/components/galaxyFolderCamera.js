import { buildFolderScene } from './galaxyFolderScene.js';
import { CAMERA } from './galaxyTuning.js';
import {
  easeInOutCubic, easeInOutQuad, easeOutCubic, easeOutQuad, easeLagged,
} from './galaxyEasing.js';

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

/**
 * Fly-out (back navigation): shrink out of the current scene, then swap to
 * the parent scene atomically at `swapAt` and grow the bloom in. The swap
 * (clearing zoom/focus refs, installing the new scene, resetting the
 * camera) happens in one place so nothing can observe a half-swapped state.
 */
function advanceFlyOut(fly, cam, refs, params) {
  const { W, H, saveNav } = params;
  const gt = fly.t;
  const tFz = fly._targetFz || 1;
  let sceneAlpha = 1;
  let bloomAlpha = 0;

  const swapAt = FLY_OUT.swapAt;
  if (gt < swapAt) {
    const p = gt / swapAt;
    cam.z = fly.sz * (1 - p * FLY_OUT.shrinkFraction);
    sceneAlpha = 1 - p * FLY_OUT.fadeFraction;
  }
  if (gt >= swapAt && !fly.swapped) {
    fly.swapped = true;
    refs.zoomedFileRef.current = null;
    refs.focusedFolderRef.current = null;
    refs.navRef.current = { path: [...fly.newPath] };
    refs.sceneRef.current = refs.nextSceneRef.current;
    refs.sceneRef.current._node = fly.newPath[fly.newPath.length - 1];
    refs.nextSceneRef.current = null;
    refs.frameCount.current = 0;
    cam.x = W / 2; cam.y = H / 2; cam.z = tFz * FLY_OUT.bloomZoomRatio;
    saveNav();
  }
  if (gt >= swapAt) {
    const p = (gt - swapAt) / (1 - swapAt);
    const pe = easeOutQuad(p);
    const openZ = tFz * FLY_OUT.bloomZoomRatio;
    cam.z = openZ + (tFz - openZ) * pe;
    sceneAlpha = 0;
    bloomAlpha = FLY_OUT.bloomAlphaMin + FLY_OUT.bloomAlphaSpan * pe;
  }

  return { sceneAlpha, bloomAlpha };
}

/**
 * Fly-in (enter folder): zoom into the clicked star, then swap to its child
 * scene atomically at `swapAt` and shrink the bloom out. The swap happens in
 * one place, same as advanceFlyOut.
 */
function advanceFlyIn(fly, cam, refs, params) {
  const { W, H, saveNav } = params;
  const gt = fly.t;
  const tFz = fly._targetFz || 1;
  let sceneAlpha = 1;
  let bloomAlpha = 0;

  const swapAt = FLY_IN.swapAt;
  if (gt < swapAt) {
    const p = gt / swapAt;
    const pe = easeInOutQuad(p);
    cam.x = fly.sx + (fly.starX - fly.sx) * pe;
    cam.y = fly.sy + (fly.starY - fly.sy) * pe;
    cam.z = fly.sz + (fly.sz * FLY_IN.zoomRatio - fly.sz) * pe;
    sceneAlpha = 1 - pe * FLY_IN.fadeFraction;
  }
  if (gt >= swapAt && !fly.swapped) {
    fly.swapped = true;
    refs.zoomedFileRef.current = null;
    refs.navRef.current = { path: [...fly.newPath] };
    refs.sceneRef.current = refs.nextSceneRef.current;
    refs.sceneRef.current._node = fly.targetNode || fly.newPath[fly.newPath.length - 1];
    refs.nextSceneRef.current = null;
    refs.frameCount.current = 0;
    cam.x = W / 2; cam.y = H / 2; cam.z = tFz * FLY_IN.bloomZoomRatio;
    saveNav();
  }
  if (gt >= swapAt) {
    const p = (gt - swapAt) / (1 - swapAt);
    const pe = easeOutCubic(p);
    const openZ = tFz * FLY_IN.bloomZoomRatio;
    cam.z = openZ + (tFz - openZ) * pe;
    sceneAlpha = 0;
    bloomAlpha = FLY_IN.bloomAlphaMin + FLY_IN.bloomAlphaSpan * pe;
  }

  return { sceneAlpha, bloomAlpha };
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
  const anim = refs.animRef.current;
  refs.frameCount.current++;

  if (!anim && refs.frameCount.current <= CAMERA.snapFrames) {
    cam.x = tg.x; cam.y = tg.y; cam.z = tg.z;
  } else if (!anim) {
    cam.x += (tg.x - cam.x) * IDLE_LERP_FRACTION;
    cam.y += (tg.y - cam.y) * IDLE_LERP_FRACTION;
    cam.z += (tg.z - cam.z) * IDLE_LERP_FRACTION;
  } else {
    anim.t = Math.min(1, anim.t + CAMERA.frameStepS / TRANS);
    const ease = easeInOutCubic(anim.t);
    const lagE = easeLagged(anim.t);
    const posE = anim.out ? ease : lagE;
    const zoomE = anim.out ? lagE : ease;
    cam.x = anim.sx + (tg.x - anim.sx) * posE;
    cam.y = anim.sy + (tg.y - anim.sy) * posE;
    cam.z = anim.sz + (tg.z - anim.sz) * zoomE;
    if (anim.t >= 1) {
      refs.animRef.current = null;
      refs.prevNavRef.current = null;
      // Auto-enter focused folder after zoom completes
      const ff3 = refs.focusedFolderRef.current;
      if (ff3 && ff3.autoEnter && !refs.flyRef.current) {
        const curScene = refs.sceneRef.current || scene;
        const star = curScene.rootStars[ff3.starIdx];
        if (star && star.isFolder) {
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
      }
    }
  }
}
