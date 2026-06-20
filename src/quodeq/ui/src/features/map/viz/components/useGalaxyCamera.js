import { useRef, useEffect, useCallback } from 'react';
import { drawFrame } from './galaxyViewDraw.js';

const TRANSITION_DURATION_S = 0.8;

/* ── Animation helpers ── */

function updateStarPositions(stars, W, H, SP, t) {
  stars.forEach((s, i) => {
    if (s._clusterCx !== undefined) {
      const drift = Math.sin(t * 0.015 + i * 1.1) * 2;
      s.x = W / 2 + s._clusterCx + s._ox + drift;
      s.y = H / 2 + s._clusterCy + s._oy + Math.cos(t * 0.012 + i * 0.8) * 2;
    } else {
      const a = s.ba + Math.sin(t * 0.02 + i * 0.7) * 0.03;
      s.x = W / 2 + Math.cos(a) * (SP + s.j);
      s.y = H / 2 + Math.sin(a) * (SP + s.j);
    }
  });
}

function updatePrinciplePositions(principles, dim, t) {
  (principles || []).forEach((p, pi) => {
    const speed = 0.008 + pi * 0.003;
    const wobble = Math.sin(t * 0.04 + pi * 2.1) * 0.02;
    p.x = dim.x + Math.cos(p.ba + t * speed + wobble) * p.od;
    p.y = dim.y + Math.sin(p.ba + t * speed + wobble) * p.od;
  });
}

function interpolateCamera(cam, tg, anim, frameCount) {
  if (!anim && frameCount <= 3) {
    cam.x = tg.x; cam.y = tg.y; cam.z = tg.z;
  } else if (!anim) {
    cam.x += (tg.x - cam.x) * 0.06;
    cam.y += (tg.y - cam.y) * 0.06;
    cam.z += (tg.z - cam.z) * 0.06;
  } else {
    anim.t = Math.min(1, anim.t + 0.016 / TRANSITION_DURATION_S);
    const ease = anim.t < 0.5 ? 4 * anim.t * anim.t * anim.t : 1 - Math.pow(-2 * anim.t + 2, 3) / 2;
    const lag = Math.pow(anim.t, 0.7); const lagE = lag * lag * (3 - 2 * lag);
    const posE = anim.out ? ease : lagE;
    const zoomE = anim.out ? lagE : ease;
    cam.x = anim.sx + (tg.x - anim.sx) * posE;
    cam.y = anim.sy + (tg.y - anim.sy) * posE;
    cam.z = anim.sz + (tg.z - anim.sz) * zoomE;
    return anim.t >= 1;
  }
  return false;
}

/**
 * Manages camera state, target computation, and the animation loop for GalaxyView.
 */
export function useGalaxyCamera({ canvasRef, scene, size, showLabels, savedNavRef, savedCamRef, navRef, prevNavRef, animRef, mouseRef, hoveredRef, frameRef }) {
  const camRef = useRef(savedCamRef.current ? { ...savedCamRef.current } : null);
  const frameCount = useRef(0);
  const timeRef = useRef(0);

  const w2s = useCallback((wx, wy) => {
    const cam = camRef.current;
    return { x: (wx - cam.x) * cam.z + size.w / 2, y: (wy - cam.y) * cam.z + size.h / 2 };
  }, [size.w, size.h]);

  const getFitZoom = useCallback(() => {
    const ext = scene?._maxExtent;
    if (!ext || ext <= 0) return 1;
    const halfView = Math.min(size.w, size.h) / 2 - 20;
    return Math.min(halfView / ext, 4);
  }, [scene, size.w, size.h]);

  const getTarget = useCallback(() => {
    const nav = navRef.current;
    const fz = getFitZoom();
    if (nav.depth === 0) {
      if (nav.clusterCx != null) {
        const con = scene?.constellations?.find(c => c.cx === nav.clusterCx && c.cy === nav.clusterCy);
        const clusterExtent = con ? con.spread + 15 : 80;
        const halfView = Math.min(size.w, size.h) / 2 - 30;
        const clusterFz = halfView / clusterExtent;
        return { x: size.w / 2 + nav.clusterCx, y: size.h / 2 + nav.clusterCy, z: clusterFz };
      }
      return { x: size.w / 2, y: size.h / 2, z: fz };
    }
    if (nav.depth === 1 && nav.dim !== null) { const s = scene.stars?.[nav.dim]; if (!s) return { x: size.w / 2, y: size.h / 2, z: fz }; return { x: s.x, y: s.y, z: 5 }; }
    if (nav.depth === 2 && nav.dim !== null && nav.prin !== null) { const s = scene.stars?.[nav.dim]; const p = s ? scene.principles?.[nav.dim]?.[nav.prin] : null; if (!p) return { x: size.w / 2, y: size.h / 2, z: fz }; return { x: p.x, y: p.y, z: 50 }; }
    return camRef.current;
  }, [scene, size.w, size.h, getFitZoom, navRef]);

  const startTransition = useCallback((zoomingOut = false) => {
    const cam = camRef.current;
    animRef.current = { t: 0, sx: cam.x, sy: cam.y, sz: cam.z, out: zoomingOut };
  }, [animRef]);

  // Main animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !scene) return;
    const ctx = canvas.getContext('2d');
    let running = true;

    if (camRef.current?._sceneId !== scene) {
      camRef.current = null;
      frameCount.current = 0;
    }

    function frame() {
      if (!running) return;
      const t = timeRef.current += 0.016;
      const nav = navRef.current;
      const W = size.w, H = size.h;
      const SP = Math.min(W, H) * 0.22;
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
      const done = interpolateCamera(cam, tg, anim, frameCount.current);
      if (done) { animRef.current = null; prevNavRef.current = null; }

      const { hovered } = drawFrame(ctx, scene, cam, nav, {
        W, H, t,
        mx: mouseRef.current.x, my: mouseRef.current.y,
        showLabels, animating: !!anim,
        rDim, rPrin, w2s,
        parentEl: canvasRef.current?.parentElement,
      });
      hoveredRef.current = hovered;

      frameRef.current = requestAnimationFrame(frame);
    }

    frameRef.current = requestAnimationFrame(frame);
    return () => { running = false; cancelAnimationFrame(frameRef.current); };
  }, [scene, size, showLabels, w2s, getTarget, canvasRef, navRef, prevNavRef, animRef, mouseRef, hoveredRef, frameRef, getFitZoom]);

  return { camRef, w2s, startTransition, getTarget };
}
