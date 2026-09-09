import { useRef, useEffect, useMemo, useCallback, useState } from 'react';
import { buildScene, updateSceneLiveData } from './galaxyViewScene.js';
import { updateTooltip, handleCanvasClick, createKeyboardHandlers } from './galaxyViewEvents.js';
import { computeLevelInfo, buildBreadcrumb } from './galaxyViewInfo.jsx';
import { useGalaxyCamera } from './useGalaxyCamera.js';

/* ── The scene: layout build + live-data refresh ── */

function useGalaxyScene({ dimensions, standardTypes }) {
  const dimKey = useMemo(() => dimensions.map(d => d.dimension).sort().join('|'), [dimensions]);
  const typesKey = useMemo(() => Object.keys(standardTypes).sort().join('|'), [standardTypes]);
  const scene = useMemo(() => {
    if (dimensions.length === 0) return null;
    return buildScene(dimensions, 800, 600, standardTypes);
  }, [dimKey, typesKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useMemo(() => {
    if (scene && dimensions.length > 0) updateSceneLiveData(scene, dimensions);
  }, [dimensions, scene]); // eslint-disable-line react-hooks/exhaustive-deps

  return scene;
}

/* ── Canvas box size, observed from the parent element ── */

function useCanvasSize(canvasRef) {
  const [size, setSize] = useState({ w: 800, h: 600 });
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
  return size;
}

/* ── Every long-lived ref the nav/camera/event code shares, plus the
      navVersion counter and the aria-live announcer ── */

function useGalaxyNavRefs() {
  const savedNavRef = useRef(null);
  const savedCamRef = useRef(null);
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
  return {
    savedNavRef, savedCamRef, navRef, animRef, navVersion, setNavVersion, mouseRef,
    hoveredRef, focusedIdxRef, tooltipRef, frameRef, prevNavRef, liveMsg, announce,
  };
}

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

  const handlerParams = useMemo(
    () => ({ scene, size, navigateTo, startTransition, saveNav, w2s, announce }),
    [scene, size, navigateTo, startTransition, saveNav, w2s, announce],
  );

  const handleClick = useCallback((e) => {
    handleCanvasClick(e, { hoveredRef, navRef, animRef, camRef, canvasRef }, handlerParams);
  }, [hoveredRef, navRef, animRef, camRef, canvasRef, handlerParams]);

  const goToDepth = useCallback((d) => {
    const nav = navRef.current;
    if (d >= nav.depth) return;
    if (d <= 0) navigateTo(0);
    else if (d === 1) navigateTo(1, nav.dim);
  }, [navRef, navigateTo]);

  const { handleKeyDown, handleFocus, handleBlur } = useMemo(
    () => createKeyboardHandlers({ navRef, animRef, focusedIdxRef }, handlerParams),
    [navRef, animRef, focusedIdxRef, handlerParams],
  );

  return { handleMouseMove, handleMouseLeave, navigateTo, handleClick, goToDepth, handleKeyDown, handleFocus, handleBlur };
}

/** Composes the scene, canvas size, nav refs, camera and event handlers into
 * the view data GalaxyView renders from. Mirrors useGalaxyFolderViewModel. */
export function useGalaxyViewModel({ dimensions, standardTypes, showLabels, resetKey, projectName, onNavigate }) {
  // Guard against an omitted or null `dimensions` prop: normalize to an empty
  // array so the memos below don't crash on `.map()`/`.length`.
  const safeDimensions = dimensions ?? [];
  const canvasRef = useRef(null);
  const size = useCanvasSize(canvasRef);
  const scene = useGalaxyScene({ dimensions: safeDimensions, standardTypes });
  const {
    savedNavRef, savedCamRef, navRef, animRef, navVersion, setNavVersion, mouseRef,
    hoveredRef, focusedIdxRef, tooltipRef, frameRef, prevNavRef, liveMsg, announce,
  } = useGalaxyNavRefs();

  // camRef is bound below by useGalaxyCamera; this closure only reads it when
  // called, which is always after that line has run.
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

  const handlers = useGalaxyHandlers({
    canvasRef, navRef, animRef, camRef, hoveredRef, mouseRef, tooltipRef, prevNavRef, focusedIdxRef, announce,
    scene, size, startTransition, saveNav, w2s,
  });

  const breadcrumb = useMemo(() => buildBreadcrumb(scene, navRef.current, projectName), [scene, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps
  const levelInfo = useMemo(() => computeLevelInfo(scene, navRef.current, projectName, onNavigate, navRef), [scene, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  return { scene, size, canvasRef, tooltipRef, liveMsg, breadcrumb, levelInfo, handlers, startTransition, saveNav };
}
