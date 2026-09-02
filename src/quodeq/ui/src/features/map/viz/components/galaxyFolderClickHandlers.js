import { getThemeColors } from '../core/galaxyCore.js';
import { buildFolderScene } from './galaxyFolderScene.js';

/** Click on a hovered star: focus a folder (or drop focus if already
 * focused), or zoom into a file. */
export function handleNodeClick(refs, h, { startTransition, saveNav }) {
  if (h.type === 'folder') {
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
  if (h.type === 'file') {
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
  const tx = nearestStar ? wx * 0.3 + nearestStar.x * 0.7 : wx;
  const ty = nearestStar ? wy * 0.3 + nearestStar.y * 0.7 : wy;
  const newZ = cam.z * 2.5;
  const maxZ = getFitZoom(curScene) * 10;
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

/** Click on empty space: zoom out of whatever is focused/zoomed, else
 * zoom toward the cursor at the root, else fly back to the parent folder. */
export function handleEmptySpaceClick(refs, nav, params) {
  const { startTransition, saveNav, getFitZoom, scene, size } = params;
  if (refs.zoomedFileRef.current) {
    refs.zoomedFileRef.current = null;
    refs.zoomTargetRef.current = null;
    startTransition(true);
    saveNav();
  } else if (refs.zoomTargetRef.current) {
    refs.zoomTargetRef.current = null;
    startTransition(true);
    saveNav();
  } else if (refs.focusedFolderRef.current) {
    refs.focusedFolderRef.current = null;
    startTransition(true);
    saveNav();
  } else if (nav.path.length <= 1) {
    zoomTowardCursor(refs, { startTransition, saveNav, getFitZoom, scene, size });
  } else if (nav.path.length > 1) {
    flyBackToParent(refs, nav, size);
  }
}
