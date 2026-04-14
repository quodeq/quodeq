import { useRef, useEffect, useMemo, useCallback, useState } from 'react';
import { invalidateThemeColors, LEGEND_ITEMS } from '../core/galaxyCore.js';
import VizBreadcrumb from './VizBreadcrumb.jsx';
import { buildScene, updateSceneLiveData } from './galaxyViewScene.js';
import { drawFrame } from './galaxyViewDraw.js';
import { updateTooltip, handleCanvasClick } from './galaxyViewEvents.js';
import { computeLevelInfo, buildBreadcrumb, LevelInfoPanel } from './galaxyViewInfo.jsx';

const TRANSITION_DURATION_S = 0.8;

/* ── Animation helpers (extracted from frame loop) ── */

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

/* ── Custom hook: mouse/click handler setup ── */

function useGalaxyHandlers({ canvasRef, navRef, animRef, camRef, hoveredRef, mouseRef, tooltipRef, prevNavRef, scene, size, startTransition, saveNav, w2s }) {
  const handleMouseMove = useCallback((e) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    canvasRef.current.style.cursor = hoveredRef.current && navRef.current.depth < 2 ? 'pointer' : 'default';
    updateTooltip(tooltipRef.current, hoveredRef.current, !!animRef.current, e.clientX, e.clientY);
  }, [canvasRef, mouseRef, hoveredRef, navRef, tooltipRef, animRef]);

  const handleMouseLeave = useCallback(() => {
    mouseRef.current = { x: -1, y: -1 };
    hoveredRef.current = null;
    if (tooltipRef.current) tooltipRef.current.style.display = 'none';
  }, [mouseRef, hoveredRef, tooltipRef]);

  const navigateTo = useCallback((depth, dim, prin) => {
    if (animRef.current) return;
    const wasDepth = navRef.current.depth;
    const zoomingOut = depth < wasDepth;
    if (zoomingOut) prevNavRef.current = { ...navRef.current };
    navRef.current = { depth, dim: dim ?? null, prin: prin ?? null };
    startTransition(zoomingOut);
    saveNav();
  }, [animRef, navRef, prevNavRef, saveNav, startTransition]);

  const handleClick = useCallback((e) => {
    handleCanvasClick(e, { hoveredRef, navRef, animRef, camRef, canvasRef }, scene, size, navigateTo, startTransition, saveNav, w2s);
  }, [hoveredRef, navRef, animRef, camRef, canvasRef, navigateTo, startTransition, saveNav, scene, size, w2s]);

  const goToDepth = useCallback((d) => {
    const nav = navRef.current;
    if (d >= nav.depth) return;
    if (d <= 0) navigateTo(0);
    else if (d === 1) navigateTo(1, nav.dim);
  }, [navRef, navigateTo]);

  return { handleMouseMove, handleMouseLeave, navigateTo, handleClick, goToDepth };
}

export default function GalaxyView({ dimensions, onNavigate, showLabels = true, setShowLabels, darkMode, resetKey = 0, projectName = '', standardTypes = {} }) {
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  // Saved state — persists across unmount/remount (back from detail) via refs
  const savedNavRef = useRef(null);
  const savedCamRef = useRef(null);

  // Invalidate cached theme colors when dark mode toggles
  useEffect(() => { invalidateThemeColors(); }, [darkMode]);

  // Build layout once when dimension structure or standard types change
  const dimKey = useMemo(() => dimensions.map(d => d.dimension).sort().join('|'), [dimensions]);
  const typesKey = useMemo(() => Object.keys(standardTypes).sort().join('|'), [standardTypes]);
  const sceneRef = useRef(null);
  const scene = useMemo(() => {
    if (dimensions.length === 0) { sceneRef.current = null; return null; }
    const s = buildScene(dimensions, 800, 600, standardTypes);
    sceneRef.current = s;
    return s;
  }, [dimKey, typesKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Update live data (scores, violations, particles) without regenerating layout
  useMemo(() => {
    if (scene && dimensions.length > 0) updateSceneLiveData(scene, dimensions);
  }, [dimensions, scene]); // eslint-disable-line react-hooks/exhaustive-deps

  // Resize observer
  useEffect(() => {
    const el = canvasRef.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // --- Camera state (refs to avoid re-renders) ---
  const hasSavedDeep = savedNavRef.current && savedNavRef.current.depth > 0;
  const camRef = useRef(savedCamRef.current ? { ...savedCamRef.current } : null);
  const navRef = useRef(hasSavedDeep ? { ...savedNavRef.current } : { depth: 0, dim: null, prin: null });
  const animRef = useRef(null);
  const frameCount = useRef(0);
  const [navVersion, setNavVersion] = useState(0);
  const timeRef = useRef(0);
  const mouseRef = useRef({ x: -1, y: -1 });
  const hoveredRef = useRef(null);
  const tooltipRef = useRef(null);
  const frameRef = useRef(null);

  const saveNav = useCallback(() => {
    savedNavRef.current = { ...navRef.current };
    savedCamRef.current = { ...camRef.current };
    setNavVersion(v => v + 1);
  }, []);

  const prevNavRef = useRef(null);
  const startTransition = useCallback((zoomingOut = false) => {
    const cam = camRef.current;
    animRef.current = { t: 0, sx: cam.x, sy: cam.y, sz: cam.z, out: zoomingOut };
  }, []);

  // Reset on resetKey change (tab re-click)
  const prevResetKey = useRef(resetKey);
  useEffect(() => {
    if (resetKey !== prevResetKey.current) {
      prevResetKey.current = resetKey;
      prevNavRef.current = { ...navRef.current };
      navRef.current = { depth: 0, dim: null, prin: null };
      savedNavRef.current = null;
      savedCamRef.current = null;
      startTransition(true);
      saveNav();
    }
  }, [resetKey, saveNav, startTransition]);

  // World-to-screen transform
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
    if (nav.depth === 1 && nav.dim !== null) { const s = scene.stars[nav.dim]; return { x: s.x, y: s.y, z: 5 }; }
    if (nav.depth === 2 && nav.dim !== null && nav.prin !== null) { const p = scene.principles[nav.dim][nav.prin]; return { x: p.x, y: p.y, z: 50 }; }
    return camRef.current;
  }, [scene, size.w, size.h, getFitZoom]);

  // --- Main animation loop ---
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
        updatePrinciplePositions(scene.principles[rDim], scene.stars[rDim], t);
      }

      // --- Camera ---
      const tg = getTarget();
      const anim = animRef.current;
      frameCount.current++;
      const done = interpolateCamera(cam, tg, anim, frameCount.current);
      if (done) { animRef.current = null; prevNavRef.current = null; }

      // --- Draw ---
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
  }, [scene, size, showLabels, w2s, getTarget]);

  // --- Mouse + click handlers (extracted to custom hook) ---
  const { handleMouseMove, handleMouseLeave, handleClick, goToDepth } = useGalaxyHandlers({
    canvasRef, navRef, animRef, camRef, hoveredRef, mouseRef, tooltipRef, prevNavRef,
    scene, size, startTransition, saveNav, w2s,
  });

  // Breadcrumb builder
  const breadcrumb = useMemo(() => buildBreadcrumb(scene, navRef.current, projectName), [scene, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Context info for current depth
  const levelInfo = useMemo(() => computeLevelInfo(scene, navRef.current, projectName, onNavigate, navRef), [scene, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fade in once constellations are ready
  const hasConstellations = scene?.constellations?.length > 0;
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (hasConstellations) setVisible(true);
  }, [hasConstellations]);

  if (!scene) return null;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', opacity: visible ? 1 : 0, transition: 'opacity 0.4s ease' }}>
      <canvas
        ref={canvasRef}
        width={size.w}
        height={size.h}
        style={{ width: '100%', height: '100%', display: 'block' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        role="img"
        aria-label="Galaxy visualization of project compliance"
      />
      {/* Breadcrumb */}
      <VizBreadcrumb items={breadcrumb.map((bc, i) => ({
        label: bc.label,
        onClick: i < breadcrumb.length - 1 ? () => {
          if (bc.action) { bc.action(); startTransition(true); saveNav(); }
          else goToDepth(bc.depth);
        } : undefined,
      }))} />
      {/* Tooltip */}
      <div
        ref={tooltipRef}
        style={{ position: 'fixed', display: 'none', background: 'color-mix(in srgb, var(--color-surface) 92%, transparent)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '10px 14px', pointerEvents: 'none', fontSize: 12, zIndex: 10, boxShadow: '0 4px 20px rgba(0,0,0,0.3)', backdropFilter: 'blur(8px)', minWidth: 140 }}
      />
      {/* Legend */}
      <div style={{ position: 'absolute', bottom: 8, left: 12, display: 'flex', gap: 14, fontSize: 11, color: 'var(--color-text-muted)', zIndex: 2 }}>
        {LEGEND_ITEMS.map(({ color, label }) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />{label}
          </span>
        ))}
      </div>
      {/* Level info panel */}
      <LevelInfoPanel levelInfo={levelInfo} />
    </div>
  );
}
