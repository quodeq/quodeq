import { buildFolderScene } from './galaxyFolderScene.js';

/**
 * Advance the fly-into/fly-out transition state.
 * Mutates fly, cam, and various refs. Returns { sceneAlpha, bloomAlpha }.
 */
export function advanceFlyTransition(fly, cam, refs, params) {
  const { W, H, FLY_DURATION, getFitZoom, saveNav } = params;
  let sceneAlpha = 1;
  let bloomAlpha = 0;

  fly.t = Math.min(1, fly.t + 0.016 / FLY_DURATION);
  const gt = fly.t;
  const ease = gt < 0.5 ? 2 * gt * gt : 1 - Math.pow(-2 * gt + 2, 2) / 2;

  if (!fly._targetFz) {
    fly._targetFz = getFitZoom(refs.nextSceneRef.current);
  }
  const tFz = fly._targetFz || 1;

  if (fly.reverse) {
    // --- FLY-OUT (back navigation) ---
    const swapAt = 0.4;
    if (gt < swapAt) {
      const p = gt / swapAt;
      cam.z = fly.sz * (1 - p * 0.7);
      sceneAlpha = 1 - p * 0.8;
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
      cam.x = W / 2; cam.y = H / 2; cam.z = tFz * 6;
      saveNav();
    }
    if (gt >= swapAt) {
      const p = (gt - swapAt) / (1 - swapAt);
      const pe = 1 - (1 - p) * (1 - p);
      cam.z = tFz * 6 + (tFz - tFz * 6) * pe;
      sceneAlpha = 0;
      bloomAlpha = 0.2 + 0.8 * pe;
    }
  } else {
    // --- FLY-IN (enter folder) ---
    const swapAt = 0.35;
    if (gt < swapAt) {
      const p = gt / swapAt;
      const pe = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      cam.x = fly.sx + (fly.starX - fly.sx) * pe;
      cam.y = fly.sy + (fly.starY - fly.sy) * pe;
      cam.z = fly.sz + (fly.sz * 4 - fly.sz) * pe;
      sceneAlpha = 1 - pe * 0.85;
    }
    if (gt >= swapAt && !fly.swapped) {
      fly.swapped = true;
      refs.zoomedFileRef.current = null;
      refs.navRef.current = { path: [...fly.newPath] };
      refs.sceneRef.current = refs.nextSceneRef.current;
      refs.sceneRef.current._node = fly.targetNode || fly.newPath[fly.newPath.length - 1];
      refs.nextSceneRef.current = null;
      refs.frameCount.current = 0;
      cam.x = W / 2; cam.y = H / 2; cam.z = tFz * 0.3;
      saveNav();
    }
    if (gt >= swapAt) {
      const p = (gt - swapAt) / (1 - swapAt);
      const pe = 1 - Math.pow(1 - p, 3);
      cam.z = tFz * 0.3 + (tFz - tFz * 0.3) * pe;
      sceneAlpha = 0;
      bloomAlpha = 0.15 + 0.85 * pe;
    }
  }

  return { sceneAlpha, bloomAlpha };
}

/**
 * Advance camera state (non-fly mode). Returns nothing, mutates cam in place.
 */
export function advanceCamera(cam, refs, params) {
  const { TRANS, scene, computeFocusCamera, saveNav, setNavVersion, getFitZoom } = params;
  const tg = computeFocusCamera();
  const anim = refs.animRef.current;
  refs.frameCount.current++;

  if (!anim && refs.frameCount.current <= 3) {
    cam.x = tg.x; cam.y = tg.y; cam.z = tg.z;
  } else if (!anim) {
    cam.x += (tg.x - cam.x) * 0.08;
    cam.y += (tg.y - cam.y) * 0.08;
    cam.z += (tg.z - cam.z) * 0.08;
  } else {
    anim.t = Math.min(1, anim.t + 0.016 / TRANS);
    const ease = anim.t < 0.5 ? 4 * anim.t * anim.t * anim.t : 1 - Math.pow(-2 * anim.t + 2, 3) / 2;
    const lag = Math.pow(anim.t, 0.7);
    const lagE = lag * lag * (3 - 2 * lag);
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
          refs.nextSceneRef.current = buildFolderScene(star._node, 800, 600);
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
