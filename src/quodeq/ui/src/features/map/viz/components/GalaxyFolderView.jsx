import { useRef, useEffect, useMemo, useCallback, useState } from 'react';
import { invalidateThemeColors, LEGEND_ITEMS } from '../core/galaxyCore.js';
import VizBreadcrumb from './VizBreadcrumb.jsx';
import { buildFolderScene, buildNavPath, buildLevelInfo } from './galaxyFolderScene.js';
import { advanceFlyTransition, advanceCamera } from './galaxyFolderCamera.js';
import {
  drawScene, drawNebula, drawStarfield, drawConstellationLines,
  drawStars, drawLabels,
} from './galaxyFolderDraw.js';
import { createEventHandlers } from './galaxyFolderEvents.js';
import GalaxyFolderPanel from './GalaxyFolderPanel.jsx';

const TRANS = 0.8;
const FLY_DURATION = 1.4;

export default function GalaxyFolderView({ node, currentPath = '', onPathChange, onFileClick, onNavigate, showLabels = true, setShowLabels, darkMode, resetKey = 0, projectName = '' }) {
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  useEffect(() => { invalidateThemeColors(); }, [darkMode]);

  // Navigation state
  const navRef = useRef(null);
  if (navRef.current === null) {
    navRef.current = { path: buildNavPath(node, currentPath) };
  }
  const savedFolderNavRef = useRef(null);  // was module-level _savedFolderNav
  const savedFolderCamRef = useRef(null);  // was module-level _savedFolderCam
  const camRef = useRef(savedFolderCamRef.current ? { ...savedFolderCamRef.current } : null);
  const animRef = useRef(null);
  const frameCount = useRef(0);
  const [navVersion, setNavVersion] = useState(0);
  const timeRef = useRef(0);
  const mouseRef = useRef({ x: -1, y: -1 });
  const hoveredRef = useRef(null);
  const tooltipRef = useRef(null);
  const frameRef = useRef(null);
  const prevNavRef = useRef(null);
  const zoomedFileRef = useRef(null);
  const focusedFolderRef = useRef(null);
  const zoomTargetRef = useRef(null);
  const flyRef = useRef(null);
  const sceneRef = useRef(null);
  const nextSceneRef = useRef(null);

  const currentNode = useMemo(() => {
    const path = navRef.current.path;
    return path[path.length - 1] || node;
  }, [node, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const scene = useMemo(() => {
    if (!currentNode) { sceneRef.current = null; return null; }
    if (sceneRef.current && sceneRef.current._node === currentNode) {
      return sceneRef.current;
    }
    const s = buildFolderScene(currentNode, 800, 600);
    s._node = currentNode;
    sceneRef.current = s;
    return s;
  }, [currentNode]);

  // Sync nav path when currentPath changes externally
  const prevSyncPath = useRef(currentPath);
  useEffect(() => {
    if (currentPath === prevSyncPath.current) return;
    prevSyncPath.current = currentPath;
    navRef.current = { path: buildNavPath(node, currentPath) };
    savedFolderNavRef.current = null;
    savedFolderCamRef.current = null;
    camRef.current = null;
    sceneRef.current = null;
    nextSceneRef.current = null;
    flyRef.current = null;
    zoomedFileRef.current = null;
    focusedFolderRef.current = null;
    setNavVersion(v => v + 1);
  }, [currentPath, node]);

  const saveNav = useCallback(() => {
    savedFolderNavRef.current = { ...navRef.current, path: [...navRef.current.path] };
    savedFolderCamRef.current = camRef.current ? { ...camRef.current } : null;
    setNavVersion(v => v + 1);
    const cur = navRef.current.path[navRef.current.path.length - 1];
    if (cur && onPathChange) onPathChange(cur.path || '');
  }, [onPathChange]);

  const startTransition = useCallback((zoomingOut = false) => {
    const cam = camRef.current;
    if (!cam) return;
    animRef.current = { t: 0, sx: cam.x, sy: cam.y, sz: cam.z, out: zoomingOut };
  }, []);

  // Reset on resetKey change
  const prevResetKey = useRef(resetKey);
  useEffect(() => {
    if (resetKey !== prevResetKey.current) {
      prevResetKey.current = resetKey;
      prevNavRef.current = null;
      zoomedFileRef.current = null;
      focusedFolderRef.current = null;
      navRef.current = { path: [node] };
      savedFolderNavRef.current = null;
      savedFolderCamRef.current = null;
      camRef.current = null;
      saveNav();
    }
  }, [resetKey, node, saveNav]);

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

  const w2s = useCallback((wx, wy) => {
    const cam = camRef.current;
    if (!cam) return { x: wx, y: wy };
    return { x: (wx - cam.x) * cam.z + size.w / 2, y: (wy - cam.y) * cam.z + size.h / 2 };
  }, [size.w, size.h]);

  const getFitZoom = useCallback((s) => {
    const ext = s?._maxExtent;
    if (!ext || ext <= 0) return 1;
    const halfView = Math.min(size.w, size.h) / 2 * 0.85;
    return Math.min(halfView / ext, 4);
  }, [size.w, size.h]);

  const computeFocusCamera = useCallback(() => {
    const fz = getFitZoom(sceneRef.current);
    const zf = zoomedFileRef.current;
    if (zf) return { x: zf.x, y: zf.y, z: Math.max(6, fz * 4) };
    const zt = zoomTargetRef.current;
    if (zt) return { x: zt.x, y: zt.y, z: zt.z };
    const ff = focusedFolderRef.current;
    if (ff) {
      const star = (sceneRef.current || scene)?.rootStars?.[ff.starIdx];
      const previewR = star ? star.radius * 4 : 30;
      const targetScreenR = Math.min(size.w, size.h) * 0.3;
      const focusZ = targetScreenR / (previewR * 0.5);
      return { x: ff.x, y: ff.y, z: Math.max(fz * 2, focusZ) };
    }
    return { x: size.w / 2, y: size.h / 2, z: fz };
  }, [size.w, size.h, getFitZoom]);

  // Refs bundle for extracted functions
  const refs = useMemo(() => ({
    navRef, camRef, animRef, frameCount, sceneRef, nextSceneRef,
    zoomedFileRef, focusedFolderRef, zoomTargetRef, flyRef,
    prevNavRef, mouseRef, hoveredRef, tooltipRef, canvasRef, frameRef,
  }), []);

  // --- Main animation loop ---
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !scene) return;
    const ctx = canvas.getContext('2d');
    let running = true;

    function frame() {
      if (!running) return;
      const t = timeRef.current += 0.016;
      const W = size.w, H = size.h;
      if (!camRef.current) camRef.current = { x: W / 2, y: H / 2, z: getFitZoom(sceneRef.current || scene) };
      const cam = camRef.current;

      const fly = flyRef.current;
      let sceneAlpha = 1, bloomAlpha = 0;
      if (fly) {
        const result = advanceFlyTransition(fly, cam, refs, {
          W, H, FLY_DURATION, getFitZoom, saveNav,
        });
        sceneAlpha = result.sceneAlpha;
        bloomAlpha = result.bloomAlpha;
        if (fly.t >= 1) {
          flyRef.current = null;
          const endFz = getFitZoom(sceneRef.current);
          cam.x = W / 2; cam.y = H / 2; cam.z = endFz;
          setNavVersion(v => v + 1);
        }
      }
      if (!flyRef.current) {
        advanceCamera(cam, refs, {
          TRANS, scene, computeFocusCamera, saveNav, setNavVersion, getFitZoom,
        });
      }

      const activeScene = sceneRef.current || scene;
      // Update star world positions
      activeScene.rootStars.forEach((s, i) => {
        const drift = Math.sin(t * 0.015 + i * 1.1) * 2;
        s.x = W / 2 + s.ox + drift;
        s.y = H / 2 + s.oy + Math.cos(t * 0.012 + i * 0.8) * 2;
      });
      if (!fly) {
        const ff2 = focusedFolderRef.current;
        if (ff2 && ff2.starIdx < activeScene.rootStars.length) {
          const fs = activeScene.rootStars[ff2.starIdx];
          ff2.x = fs.x; ff2.y = fs.y;
        }
        const zfr = zoomedFileRef.current;
        if (zfr && zfr.starIdx != null && zfr.starIdx < activeScene.rootStars.length) {
          const zfs = activeScene.rootStars[zfr.starIdx];
          zfr.x = zfs.x; zfr.y = zfs.y;
        }
      }

      const { tc } = drawScene(ctx, activeScene, { W, H, t, cam, w2s, showLabels, mouseRef, flyRef, focusedFolderRef, canvasRef });
      const activeFly = flyRef.current;
      const effectiveAlpha = activeFly
        ? (activeFly.swapped ? bloomAlpha : (activeFly.t === 0 ? 0.85 : sceneAlpha))
        : 1;
      if (effectiveAlpha < 0.01) {
        frameRef.current = requestAnimationFrame(frame);
        return;
      }
      ctx.globalAlpha = effectiveAlpha;

      const curNode = navRef.current.path[navRef.current.path.length - 1];
      drawNebula(ctx, curNode, tc, W, H, t);
      drawStarfield(ctx, activeScene.bg, tc, W, H, t);
      drawConstellationLines(ctx, activeScene, tc, w2s);

      const { pendingLabels, newHovered } = drawStars(ctx, activeScene, {
        t, cam, w2s, showLabels, mouseRef, flyRef, focusedFolderRef, animRef, tc,
      });
      drawLabels(ctx, pendingLabels, tc);

      ctx.globalAlpha = 1;
      hoveredRef.current = newHovered;
      frameRef.current = requestAnimationFrame(frame);
    }

    frameRef.current = requestAnimationFrame(frame);
    return () => { running = false; cancelAnimationFrame(frameRef.current); };
  }, [scene, size, showLabels, w2s, computeFocusCamera, getFitZoom, refs, saveNav]);

  // Event handlers
  const { handleMouseMove, handleMouseLeave, handleClick, goToPathIndex } = useMemo(
    () => createEventHandlers(refs, { startTransition, saveNav, getFitZoom, scene, size }),
    [refs, startTransition, saveNav, getFitZoom, scene, size]
  );

  // Breadcrumb
  const breadcrumb = useMemo(() => {
    const path = navRef.current.path;
    const parts = [{ label: projectName || 'Project', idx: 0 }];
    for (let i = 1; i < path.length; i++) {
      parts.push({ label: path[i].name, idx: i });
    }
    return parts;
  }, [projectName, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Level info panel data
  const levelInfo = useMemo(() => buildLevelInfo({
    scene, currentNode, zoomedFileRef, navRef, projectName, onFileClick,
  }), [scene, currentNode, projectName, onFileClick, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fade in
  const [visible, setVisible] = useState(false);
  useEffect(() => { if (scene) setVisible(true); }, [scene]);

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
        aria-label="Galaxy folder visualization of project structure"
      />
      <VizBreadcrumb items={breadcrumb.map((bc, i) => ({
        label: bc.label,
        onClick: i < breadcrumb.length - 1 ? () => goToPathIndex(bc.idx) : undefined,
      }))} />
      <div
        ref={tooltipRef}
        style={{ position: 'fixed', display: 'none', background: 'color-mix(in srgb, var(--color-surface) 92%, transparent)', border: '1px solid var(--color-border)', borderRadius: 8, padding: '10px 14px', pointerEvents: 'none', fontSize: 12, zIndex: 10, boxShadow: '0 4px 20px rgba(0,0,0,0.3)', backdropFilter: 'blur(8px)', minWidth: 140 }}
      />
      <div style={{ position: 'absolute', bottom: 8, left: 12, display: 'flex', gap: 14, fontSize: 11, color: 'var(--color-text-muted)', zIndex: 2 }}>
        {LEGEND_ITEMS.map(({ color, label }) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />{label}
          </span>
        ))}
      </div>
      <GalaxyFolderPanel levelInfo={levelInfo} />
    </div>
  );
}
