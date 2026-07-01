import { useRef, useEffect, useMemo, useCallback, useState } from 'react';
import { invalidateThemeColors, LEGEND_ITEMS } from '../core/galaxyCore.js';
import VizBreadcrumb from './VizBreadcrumb.jsx';
import { buildScene, updateSceneLiveData } from './galaxyViewScene.js';
import { updateTooltip, handleCanvasClick, createKeyboardHandlers } from './galaxyViewEvents.js';
import { computeLevelInfo, buildBreadcrumb, LevelInfoPanel } from './galaxyViewInfo.jsx';
import { useGalaxyCamera } from './useGalaxyCamera.js';

/* ── Custom hook: mouse/click handler setup ── */

function useGalaxyHandlers({ canvasRef, navRef, animRef, camRef, hoveredRef, mouseRef, tooltipRef, prevNavRef, focusedIdxRef, announce, scene, size, startTransition, saveNav, w2s }) {
  const navigateTo = useCallback((depth, dim, prin) => {
    if (animRef.current) return;
    const wasDepth = navRef.current.depth;
    const zoomingOut = depth < wasDepth;
    if (zoomingOut) prevNavRef.current = { ...navRef.current };
    navRef.current = { depth, dim: dim ?? null, prin: prin ?? null };
    startTransition(zoomingOut);
    saveNav();
  }, [animRef, navRef, prevNavRef, saveNav, startTransition]);

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

  const handleClick = useCallback((e) => {
    handleCanvasClick(e, { hoveredRef, navRef, animRef, camRef, canvasRef }, scene, size, navigateTo, startTransition, saveNav, w2s);
  }, [hoveredRef, navRef, animRef, camRef, canvasRef, navigateTo, startTransition, saveNav, scene, size, w2s]);

  const goToDepth = useCallback((d) => {
    const nav = navRef.current;
    if (d >= nav.depth) return;
    if (d <= 0) navigateTo(0);
    else if (d === 1) navigateTo(1, nav.dim);
  }, [navRef, navigateTo]);

  const { handleKeyDown, handleFocus, handleBlur } = useMemo(
    () => createKeyboardHandlers(
      { navRef, animRef, focusedIdxRef },
      { scene, navigateTo, startTransition, saveNav, announce },
    ),
    [navRef, animRef, focusedIdxRef, scene, navigateTo, startTransition, saveNav, announce],
  );

  return { handleMouseMove, handleMouseLeave, navigateTo, handleClick, goToDepth, handleKeyDown, handleFocus, handleBlur };
}

export default function GalaxyView({ dimensions, onNavigate, showLabels = true, setShowLabels, darkMode, resetKey = 0, projectName = '', standardTypes = {} }) {
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const savedNavRef = useRef(null);
  const savedCamRef = useRef(null);

  useEffect(() => { invalidateThemeColors(); }, [darkMode]);

  const dimKey = useMemo(() => dimensions.map(d => d.dimension).sort().join('|'), [dimensions]);
  const typesKey = useMemo(() => Object.keys(standardTypes).sort().join('|'), [standardTypes]);
  const scene = useMemo(() => {
    if (dimensions.length === 0) return null;
    return buildScene(dimensions, 800, 600, standardTypes);
  }, [dimKey, typesKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useMemo(() => {
    if (scene && dimensions.length > 0) updateSceneLiveData(scene, dimensions);
  }, [dimensions, scene]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const hasSavedDeep = savedNavRef.current && savedNavRef.current.depth > 0;
  const navRef = useRef(hasSavedDeep ? { ...savedNavRef.current } : { depth: 0, dim: null, prin: null });
  const animRef = useRef(null);
  const [navVersion, setNavVersion] = useState(0);
  const mouseRef = useRef({ x: -1, y: -1 });
  const hoveredRef = useRef(null);
  const focusedIdxRef = useRef(null);
  const tooltipRef = useRef(null);
  const frameRef = useRef(null);
  const prevNavRef = useRef(null);
  const [liveMsg, setLiveMsg] = useState('');
  const announce = useCallback((msg) => setLiveMsg(msg), []);

  const saveNav = useCallback(() => {
    savedNavRef.current = { ...navRef.current };
    savedCamRef.current = { ...camRef.current };
    setNavVersion(v => v + 1);
  }, []);

  const { camRef, w2s, startTransition } = useGalaxyCamera({
    canvasRef, scene, size, showLabels, savedNavRef, savedCamRef,
    navRef, prevNavRef, animRef, mouseRef, hoveredRef, focusedIdxRef, frameRef,
  });

  // Reset on resetKey change
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

  const { handleMouseMove, handleMouseLeave, handleClick, goToDepth, handleKeyDown, handleFocus, handleBlur } = useGalaxyHandlers({
    canvasRef, navRef, animRef, camRef, hoveredRef, mouseRef, tooltipRef, prevNavRef, focusedIdxRef, announce,
    scene, size, startTransition, saveNav, w2s,
  });

  const breadcrumb = useMemo(() => buildBreadcrumb(scene, navRef.current, projectName), [scene, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps
  const levelInfo = useMemo(() => computeLevelInfo(scene, navRef.current, projectName, onNavigate, navRef), [scene, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasConstellations = scene?.constellations?.length > 0;
  const [visible, setVisible] = useState(false);
  useEffect(() => { if (hasConstellations) setVisible(true); }, [hasConstellations]);

  if (!scene) return null;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', opacity: visible ? 1 : 0, transition: 'opacity 0.4s ease' }}>
      <canvas ref={canvasRef} width={size.w} height={size.h}
        className="viz-focusable"
        style={{ width: '100%', height: '100%', display: 'block' }}
        onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave} onClick={handleClick}
        tabIndex={0}
        role="application"
        aria-label="Galaxy visualization of project compliance. Use arrow keys to move between nodes, Enter to open, Escape to go back."
        onKeyDown={handleKeyDown}
        onFocus={handleFocus}
        onBlur={handleBlur} />
      <div aria-live="polite" aria-atomic="true" style={{
        position: 'absolute', width: 1, height: 1, padding: 0, margin: -1,
        overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0,
      }}>{liveMsg}</div>
      <VizBreadcrumb items={breadcrumb.map((bc, i) => ({
        label: bc.label,
        onClick: i < breadcrumb.length - 1 ? () => {
          if (bc.action) { bc.action(); startTransition(true); saveNav(); }
          else goToDepth(bc.depth);
        } : undefined,
      }))} />
      <div ref={tooltipRef}
        style={{ position: 'fixed', display: 'none', background: 'color-mix(in srgb, var(--color-surface) 92%, transparent)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '10px 14px', pointerEvents: 'none', fontSize: 12, zIndex: 10, boxShadow: '0 4px 20px rgba(0,0,0,0.3)', backdropFilter: 'blur(8px)', minWidth: 140 }} />
      <div style={{ position: 'absolute', bottom: 8, left: 12, display: 'flex', gap: 14, fontSize: 11, color: 'var(--color-text-muted)', zIndex: 2 }}>
        {LEGEND_ITEMS.map(({ color, label }) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />{label}
          </span>
        ))}
      </div>
      <LevelInfoPanel levelInfo={levelInfo} />
    </div>
  );
}
