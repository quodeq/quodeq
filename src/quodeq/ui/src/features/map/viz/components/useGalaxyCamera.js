import { useRef, useEffect, useCallback } from 'react';
import { drawFrame } from './galaxyViewDraw.js';
import { CAMERA } from './galaxyTuning.js';
import { interpolateCamera } from './galaxyCameraLerp.js';

const TRANSITION_DURATION_S = 0.8;

// Idle drift for a clustered star: sine on x, cosine on y. The speeds and
// phases are deliberately unequal so the two axes never sync into a
// straight-line wobble. One amplitude (world units) serves both axes.
const DRIFT_SPEED_X = 0.015;
const DRIFT_SPEED_Y = 0.012;
const DRIFT_PHASE_X = 1.1;
const DRIFT_PHASE_Y = 0.8;
const DRIFT_AMPLITUDE = 2;
// A star on the single-group ring instead breathes along the ring itself.
const RING_RADIUS_FRACTION = 0.22;
const RING_WOBBLE_SPEED = 0.02;
const RING_WOBBLE_PHASE = 0.7;
const RING_WOBBLE_AMPLITUDE = 0.03;
// Principles orbit their dimension star, each a little faster than the last
// so the ring never locks into a rigid wheel.
const PRINCIPLE_ORBIT_SPEED_BASE = 0.008;
const PRINCIPLE_ORBIT_SPEED_PER_INDEX = 0.003;
const PRINCIPLE_WOBBLE_SPEED = 0.04;
const PRINCIPLE_WOBBLE_PHASE = 2.1;
const PRINCIPLE_WOBBLE_AMPLITUDE = 0.02;
// Fraction of the remaining distance the idle camera covers each frame.
const IDLE_LERP_FRACTION = 0.06;
// Where each navigation depth parks the camera, and the room a cluster or
// the whole scene is given inside the viewport when fitting it.
const DIMENSION_ZOOM = 5;
const PRINCIPLE_ZOOM = 50;
const CLUSTER_RING_PAD_PX = 15;
const CLUSTER_FALLBACK_EXTENT_PX = 80;
const CLUSTER_VIEW_MARGIN_PX = 30;
const FIT_VIEW_MARGIN_PX = 20;

/* ── Animation helpers ── */

function updateStarPositions(stars, W, H, SP, t) {
  stars.forEach((s, i) => {
    if (s._clusterCx !== undefined) {
      const drift = Math.sin(t * DRIFT_SPEED_X + i * DRIFT_PHASE_X) * DRIFT_AMPLITUDE;
      s.x = W / 2 + s._clusterCx + s._ox + drift;
      s.y = H / 2 + s._clusterCy + s._oy + Math.cos(t * DRIFT_SPEED_Y + i * DRIFT_PHASE_Y) * DRIFT_AMPLITUDE;
    } else {
      const a = s.ba + Math.sin(t * RING_WOBBLE_SPEED + i * RING_WOBBLE_PHASE) * RING_WOBBLE_AMPLITUDE;
      s.x = W / 2 + Math.cos(a) * (SP + s.j);
      s.y = H / 2 + Math.sin(a) * (SP + s.j);
    }
  });
}

function updatePrinciplePositions(principles, dim, t) {
  (principles || []).forEach((p, pi) => {
    const speed = PRINCIPLE_ORBIT_SPEED_BASE + pi * PRINCIPLE_ORBIT_SPEED_PER_INDEX;
    const wobble = Math.sin(t * PRINCIPLE_WOBBLE_SPEED + pi * PRINCIPLE_WOBBLE_PHASE) * PRINCIPLE_WOBBLE_AMPLITUDE;
    p.x = dim.x + Math.cos(p.ba + t * speed + wobble) * p.od;
    p.y = dim.y + Math.sin(p.ba + t * speed + wobble) * p.od;
  });
}

// One animation-loop tick: advances star/camera positions, draws the frame,
// and schedules the next tick. Extracted as a factory (built once per effect
// run, called repeatedly via requestAnimationFrame) purely to keep the
// useGalaxyCamera effect body under the function-length cap.
function makeAnimationFrame({
  ctx, canvasRef, scene, size, navRef, prevNavRef, animRef, mouseRef, hoveredRef, focusedIdxRef, frameRef,
  showLabels, w2s, getTarget, getFitZoom, camRef, frameCount, timeRef, runningBox,
}) {
  return function frame() {
    if (!runningBox.current) return;
    timeRef.current += CAMERA.frameStepS;
    const t = timeRef.current;
    const nav = navRef.current;
    const W = size.w, H = size.h;
    const SP = Math.min(W, H) * RING_RADIUS_FRACTION;
    if (!camRef.current) camRef.current = { x: W / 2, y: H / 2, z: getFitZoom(), _sceneId: scene };
    const cam = camRef.current;

    updateStarPositions(scene.stars, W, H, SP, t);

    const prev = prevNavRef.current;
    const rDim = nav.dim ?? prev?.dim ?? null;
    const rPrin = nav.prin ?? prev?.prin ?? null;

    if (rDim !== null) {
      const rStar = scene.stars[rDim];
      if (rStar) updatePrinciplePositions(scene.principles[rDim], rStar, t);
    }

    const tg = getTarget();
    const anim = animRef.current;
    frameCount.current++;
    const done = interpolateCamera(cam, tg, anim, frameCount.current, TRANSITION_DURATION_S, IDLE_LERP_FRACTION);
    if (done) { animRef.current = null; prevNavRef.current = null; }

    const { hovered } = drawFrame(ctx, scene, cam, nav, {
      W, H, t,
      mx: mouseRef.current.x, my: mouseRef.current.y,
      showLabels, animating: !!anim,
      rDim, rPrin, w2s,
      focusedIdx: focusedIdxRef?.current ?? null,
      parentEl: canvasRef.current?.parentElement,
    });
    hoveredRef.current = hovered;

    frameRef.current = requestAnimationFrame(frame);
  };
}

function computeTarget({ nav, scene, size, camRef, fz }) {
  if (nav.depth === 0) {
    if (nav.clusterCx != null) {
      const con = scene?.constellations?.find(c => c.cx === nav.clusterCx && c.cy === nav.clusterCy);
      const clusterExtent = con ? con.spread + CLUSTER_RING_PAD_PX : CLUSTER_FALLBACK_EXTENT_PX;
      const halfView = Math.min(size.w, size.h) / 2 - CLUSTER_VIEW_MARGIN_PX;
      const clusterFz = halfView / clusterExtent;
      return { x: size.w / 2 + nav.clusterCx, y: size.h / 2 + nav.clusterCy, z: clusterFz };
    }
    return { x: size.w / 2, y: size.h / 2, z: fz };
  }
  if (nav.depth === 1 && nav.dim !== null) { const s = scene.stars?.[nav.dim]; if (!s) return { x: size.w / 2, y: size.h / 2, z: fz }; return { x: s.x, y: s.y, z: DIMENSION_ZOOM }; }
  if (nav.depth === 2 && nav.dim !== null && nav.prin !== null) { const s = scene.stars?.[nav.dim]; const p = s ? scene.principles?.[nav.dim]?.[nav.prin] : null; if (!p) return { x: size.w / 2, y: size.h / 2, z: fz }; return { x: p.x, y: p.y, z: PRINCIPLE_ZOOM }; }
  return camRef.current;
}

/**
 * Manages camera state, target computation, and the animation loop for GalaxyView.
 */
export function useGalaxyCamera({ canvasRef, scene, size, showLabels, savedCamRef, navRef, prevNavRef, animRef, mouseRef, hoveredRef, focusedIdxRef, frameRef }) {
  const camRef = useRef(savedCamRef.current ? { ...savedCamRef.current } : null);
  const frameCount = useRef(0);
  const timeRef = useRef(0);

  const w2s = useCallback((wx, wy) => {
    const cam = camRef.current;
    // The animation loop sets camRef.current on its first tick; a caller
    // (event handler, early render) invoking this before that tick has run
    // gets a neutral origin rather than a crash.
    if (!cam) return { x: 0, y: 0 };
    return { x: (wx - cam.x) * cam.z + size.w / 2, y: (wy - cam.y) * cam.z + size.h / 2 };
  }, [size.w, size.h]);

  const getFitZoom = useCallback(() => {
    const ext = scene?._maxExtent;
    if (!ext || ext <= 0) return 1;
    const halfView = Math.min(size.w, size.h) / 2 - FIT_VIEW_MARGIN_PX;
    return Math.min(halfView / ext, CAMERA.fitZoomMax);
  }, [scene, size.w, size.h]);

  const getTarget = useCallback(
    () => computeTarget({ nav: navRef.current, scene, size, camRef, fz: getFitZoom() }),
    [scene, size.w, size.h, getFitZoom, navRef],
  );

  const startTransition = useCallback((zoomingOut = false) => {
    const cam = camRef.current;
    // No camera yet (before the first animation frame): there is nothing to
    // transition from, so there is nothing to do.
    if (!cam) return;
    animRef.current = { t: 0, sx: cam.x, sy: cam.y, sz: cam.z, out: zoomingOut };
  }, [animRef]);

  // Main animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !scene) return;
    const ctx = canvas.getContext('2d');
    const runningBox = { current: true };

    if (camRef.current?._sceneId !== scene) {
      camRef.current = null;
      frameCount.current = 0;
    }

    const frame = makeAnimationFrame({
      ctx, canvasRef, scene, size, navRef, prevNavRef, animRef, mouseRef, hoveredRef, focusedIdxRef, frameRef,
      showLabels, w2s, getTarget, getFitZoom, camRef, frameCount, timeRef, runningBox,
    });

    frameRef.current = requestAnimationFrame(frame);
    return () => { runningBox.current = false; cancelAnimationFrame(frameRef.current); };
  }, [scene, size, showLabels, w2s, getTarget, canvasRef, navRef, prevNavRef, animRef, mouseRef, hoveredRef, focusedIdxRef, frameRef, getFitZoom]);

  return { camRef, w2s, startTransition, getTarget };
}
