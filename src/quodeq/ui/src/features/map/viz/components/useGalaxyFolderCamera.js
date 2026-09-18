import { useRef, useState, useCallback, useEffect } from 'react';
import { advanceFlyTransition, advanceCamera } from './galaxyFolderCamera.js';
import {
  drawScene, drawNebula, drawStarfield, drawConstellationLines,
  drawStars, drawLabels,
} from './galaxyFolderDraw.js';
import { DEFAULT_CANVAS_W, DEFAULT_CANVAS_H } from '../core/galaxyTunables.js';

const TRANS = 0.8;
const FLY_DURATION = 1.4;
// Idle star drift: sine on x, cosine on y. Speeds and phases are
// intentionally unequal so the two axes never sync into a straight-line
// wobble. One amplitude (world units) serves both axes.
const DRIFT_SPEED_X = 0.015;
const DRIFT_SPEED_Y = 0.012;
const DRIFT_PHASE_X = 1.1;
const DRIFT_PHASE_Y = 0.8;
const DRIFT_AMPLITUDE = 2;

/** Advance the fly transition (if one is running) and, once it's not, the
 * idle/focus camera lerp. Returns the alpha values the draw pass needs. */
function advanceFrameCamera(cam, fly, refs, scene, opts) {
  const { W, H, getFitZoom, computeFocusCamera, saveNav, setNavVersion } = opts;
  let sceneAlpha = 1;
  let bloomAlpha = 0;
  if (fly) {
    const result = advanceFlyTransition(fly, cam, refs, { W, H, FLY_DURATION, getFitZoom, saveNav });
    sceneAlpha = result.sceneAlpha;
    bloomAlpha = result.bloomAlpha;
    if (fly.t >= 1) {
      refs.flyRef.current = null;
      const endFz = getFitZoom(refs.sceneRef.current);
      cam.x = W / 2; cam.y = H / 2; cam.z = endFz;
      setNavVersion(v => v + 1);
    }
  }
  if (!refs.flyRef.current) {
    advanceCamera(cam, refs, { TRANS, scene, computeFocusCamera, saveNav, setNavVersion, getFitZoom, W, H });
  }
  return { sceneAlpha, bloomAlpha };
}

/** Drift the stars' world positions, then (outside a fly transition) keep
 * the focused-folder/zoomed-file preview anchors glued to their star. */
function updateStarPositions(activeScene, frame, fly, refs) {
  const { t, W, H } = frame;
  activeScene.rootStars.forEach((s, i) => {
    const drift = Math.sin(t * DRIFT_SPEED_X + i * DRIFT_PHASE_X) * DRIFT_AMPLITUDE;
    s.x = W / 2 + s.ox + drift;
    s.y = H / 2 + s.oy + Math.cos(t * DRIFT_SPEED_Y + i * DRIFT_PHASE_Y) * DRIFT_AMPLITUDE;
  });
  if (fly) return;
  const ff2 = refs.focusedFolderRef.current;
  if (ff2 && ff2.starIdx < activeScene.rootStars.length) {
    const fs = activeScene.rootStars[ff2.starIdx];
    ff2.x = fs.x; ff2.y = fs.y;
  }
  const zfr = refs.zoomedFileRef.current;
  if (zfr && zfr.starIdx != null && zfr.starIdx < activeScene.rootStars.length) {
    const zfs = activeScene.rootStars[zfr.starIdx];
    zfr.x = zfs.x; zfr.y = zfs.y;
  }
}

/** The whole draw pass for one frame: background, nebula, starfield,
 * constellation lines, stars + labels. Skips drawing (but not scheduling
 * the next frame — the caller always does that) while a fly transition is
 * still nearly invisible. `frame` is { W, H, t, cam, w2s, showLabels }, the
 * per-frame bundle every draw* helper reads from. */
function renderFrame(ctx, activeScene, frame, refs, alphas) {
  const { w2s } = frame;
  const { sceneAlpha, bloomAlpha } = alphas;
  const { tc } = drawScene(ctx, activeScene, {
    ...frame, mouseRef: refs.mouseRef, flyRef: refs.flyRef,
    focusedFolderRef: refs.focusedFolderRef, canvasRef: refs.canvasRef,
  });
  const activeFly = refs.flyRef.current;
  const effectiveAlpha = activeFly
    ? (activeFly.swapped ? bloomAlpha : (activeFly.t === 0 ? 0.85 : sceneAlpha))
    : 1;
  if (effectiveAlpha < 0.01) return;
  ctx.globalAlpha = effectiveAlpha;

  const curNode = refs.navRef.current.path[refs.navRef.current.path.length - 1];
  drawNebula(ctx, curNode, tc, frame);
  drawStarfield(ctx, activeScene.bg, tc, frame);
  drawConstellationLines(ctx, activeScene, tc, w2s);

  const { pendingLabels, newHovered } = drawStars(ctx, activeScene, {
    ...frame, mouseRef: refs.mouseRef, flyRef: refs.flyRef,
    focusedFolderRef: refs.focusedFolderRef, animRef: refs.animRef, tc,
  });
  drawLabels(ctx, pendingLabels, tc);

  ctx.globalAlpha = 1;
  refs.hoveredRef.current = newHovered;
}

/** Screen size (via a ResizeObserver on the canvas's parent) + the
 * world<->screen projection and fit-zoom math that depend on it. */
function useFolderCameraSizing(refs) {
  const [size, setSize] = useState({ w: DEFAULT_CANVAS_W, h: DEFAULT_CANVAS_H });

  useEffect(() => {
    const el = refs.canvasRef.current?.parentElement;
    if (!el) return undefined;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const w2s = useCallback((wx, wy) => {
    const cam = refs.camRef.current;
    if (!cam) return { x: wx, y: wy };
    return { x: (wx - cam.x) * cam.z + size.w / 2, y: (wy - cam.y) * cam.z + size.h / 2 };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.w, size.h]);

  const getFitZoom = useCallback((s) => {
    const ext = s?._maxExtent;
    if (!ext || ext <= 0) return 1;
    const halfView = Math.min(size.w, size.h) / 2 * 0.85;
    return Math.min(halfView / ext, 4);
  }, [size.w, size.h]);

  return { size, w2s, getFitZoom };
}

/** Where the camera should be heading right now: a zoomed file, an
 * explicit zoom target, a focused folder (previewing before auto-enter),
 * or the fit-everything default. */
function useComputeFocusCamera(refs, scene, size, getFitZoom) {
  return useCallback(() => {
    const fz = getFitZoom(refs.sceneRef.current);
    const zf = refs.zoomedFileRef.current;
    if (zf) return { x: zf.x, y: zf.y, z: Math.max(6, fz * 4) };
    const zt = refs.zoomTargetRef.current;
    if (zt) return { x: zt.x, y: zt.y, z: zt.z };
    const ff = refs.focusedFolderRef.current;
    if (ff) {
      const star = (refs.sceneRef.current || scene)?.rootStars?.[ff.starIdx];
      const previewR = star ? star.radius * 4 : 30;
      const targetScreenR = Math.min(size.w, size.h) * 0.3;
      const focusZ = targetScreenR / (previewR * 0.5);
      return { x: ff.x, y: ff.y, z: Math.max(fz * 2, focusZ) };
    }
    return { x: size.w / 2, y: size.h / 2, z: fz };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.w, size.h, getFitZoom]);
}

/**
 * The camera: screen sizing (via useFolderCameraSizing), the focus-target
 * math, and the whole canvas animation loop (camera lerp, fly transitions,
 * star drift, drawing). Everything here reads/writes the `refs` bundle
 * `useGalaxyFolderNav` builds, so nav state and camera state stay one
 * source of truth. Returns `{ size, w2s, getFitZoom }` — the pieces the
 * component and event handlers still need directly.
 */
export function useGalaxyFolderCamera({ refs, scene, showLabels, saveNav, setNavVersion }) {
  const { size, w2s, getFitZoom } = useFolderCameraSizing(refs);
  const timeRef = useRef(0);
  const computeFocusCamera = useComputeFocusCamera(refs, scene, size, getFitZoom);

  // Main animation loop
  useEffect(() => {
    const canvas = refs.canvasRef.current;
    if (!canvas || !scene) return undefined;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;
    let running = true;

    function frame() {
      if (!running) return;
      const t = timeRef.current += 0.016;
      const W = size.w, H = size.h;
      if (!refs.camRef.current) refs.camRef.current = { x: W / 2, y: H / 2, z: getFitZoom(refs.sceneRef.current || scene) };
      const cam = refs.camRef.current;
      const fly = refs.flyRef.current;

      const alphas = advanceFrameCamera(cam, fly, refs, scene, { W, H, getFitZoom, computeFocusCamera, saveNav, setNavVersion });

      const activeScene = refs.sceneRef.current || scene;
      const frameCtx = { W, H, t, cam, w2s, showLabels };
      updateStarPositions(activeScene, frameCtx, fly, refs);
      renderFrame(ctx, activeScene, frameCtx, refs, alphas);

      refs.frameRef.current = requestAnimationFrame(frame);
    }

    refs.frameRef.current = requestAnimationFrame(frame);
    return () => { running = false; cancelAnimationFrame(refs.frameRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, size, showLabels, w2s, computeFocusCamera, getFitZoom, refs, saveNav]);

  return { size, w2s, getFitZoom };
}
