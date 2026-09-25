import { getThemeColors } from '../core/galaxyCore.js';
import { HIT_TARGET_TYPE } from '../core/galaxyHitTypes.js';
import { buildFolderScene } from './galaxyFolderScene.js';

// A click on empty space near a star should read as "zoom in on that star",
// so the target is weighted toward the star rather than the raw cursor.
const CURSOR_WEIGHT = 0.3;
const NEAREST_STAR_WEIGHT = 0.7;
// Each such click multiplies the zoom by this, capped at MAX_ZOOM_FIT_MULTIPLES.
const ZOOM_STEP_MULTIPLIER = 2.5;
// Zoom-toward-cursor cap, in multiples of the scene's fit zoom.
const MAX_ZOOM_FIT_MULTIPLES = 10;

/** Click on a hovered star: focus a folder (or drop focus if already
 * focused), or zoom into a file. */
export function handleNodeClick(refs, h, { startTransition, saveNav }) {
  if (h.type === HIT_TARGET_TYPE.FOLDER) {
    const s = h.data;
    const ff = refs.focusedFolderRef.current;
    if (ff && ff.starIdx === h.starIdx) {
      return;
    } else {
      refs.zoomedFileRef.current = null;
      refs.zoomTargetRef.current = null;
      refs.focusedFolderRef.current = { x: s.x, y: s.y, starIdx: h.starIdx, data: s, autoEnter: true };
      startTransition(false);
      saveNav();
    }
    return;
  }
  if (h.type === HIT_TARGET_TYPE.FILE) {
    const s = h.data;
    refs.focusedFolderRef.current = null;
    refs.zoomTargetRef.current = null;
    refs.zoomedFileRef.current = { x: s.x, y: s.y, starIdx: h.starIdx, data: s };
    startTransition(false);
    saveNav();
  }
}

/** Zoom toward the cursor when nothing is focused/zoomed and we're at the
 * root: bias the target between the raw cursor position and the nearest
 * star so a near-miss click still reads as "zoom in on that star". */
function zoomTowardCursor(refs, { startTransition, saveNav, getFitZoom, scene, size }) {
  const cam = refs.camRef.current;
  if (!cam || refs.mouseRef.current.x < 0) return;
  const wx = (refs.mouseRef.current.x - size.w / 2) / cam.z + cam.x;
  const wy = (refs.mouseRef.current.y - size.h / 2) / cam.z + cam.y;
  const curScene = refs.sceneRef.current || scene;
  let nearestStar = null, nearestD = Infinity;
  if (curScene) {
    curScene.rootStars.forEach(s => {
      const dx = s.x - wx, dy = s.y - wy;
      const d = dx * dx + dy * dy;
      if (d < nearestD) { nearestD = d; nearestStar = s; }
    });
  }
  const tx = nearestStar ? wx * CURSOR_WEIGHT + nearestStar.x * NEAREST_STAR_WEIGHT : wx;
  const ty = nearestStar ? wy * CURSOR_WEIGHT + nearestStar.y * NEAREST_STAR_WEIGHT : wy;
  const newZ = cam.z * ZOOM_STEP_MULTIPLIER;
  const maxZ = getFitZoom(curScene) * MAX_ZOOM_FIT_MULTIPLES;
  refs.zoomTargetRef.current = { x: tx, y: ty, z: Math.min(newZ, maxZ) };
  startTransition(false);
  saveNav();
}

/** Fly back out to the parent folder's scene. */
function flyBackToParent(refs, nav, size) {
  if (refs.flyRef.current) return;
  const cam = refs.camRef.current;
  const parentPath = nav.path.slice(0, -1);
  const parentNode = parentPath[parentPath.length - 1];
  refs.nextSceneRef.current = buildFolderScene(parentNode, size.w, size.h);
  refs.flyRef.current = {
    t: 0, reverse: true,
    sx: cam.x, sy: cam.y, sz: cam.z,
    newPath: parentPath,
    starCol: getThemeColors().gradeMid,
    swapped: false,
  };
}

/** Drops the innermost zoom or focus: a zoomed file (with its zoom target),
 * else a zoom target, else a focused folder. False when none was set. */
function dropZoomOrFocus(refs) {
  if (refs.zoomedFileRef.current) {
    refs.zoomedFileRef.current = null;
    refs.zoomTargetRef.current = null;
    return true;
  }
  if (refs.zoomTargetRef.current) {
    refs.zoomTargetRef.current = null;
    return true;
  }
  if (refs.focusedFolderRef.current) {
    refs.focusedFolderRef.current = null;
    return true;
  }
  return false;
}

/** Click on empty space: zoom out of whatever is focused/zoomed, else
 * zoom toward the cursor at the root, else fly back to the parent folder. */
export function handleEmptySpaceClick(refs, nav, params) {
  const { startTransition, saveNav, getFitZoom, scene, size } = params;
  if (dropZoomOrFocus(refs)) {
    startTransition(true);
    saveNav();
  } else if (nav.path.length <= 1) {
    zoomTowardCursor(refs, { startTransition, saveNav, getFitZoom, scene, size });
  } else if (nav.path.length > 1) {
    flyBackToParent(refs, nav, size);
  }
}
