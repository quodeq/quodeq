import { useRef, useMemo, useState, useCallback, useEffect } from 'react';
import { buildFolderScene, buildNavPath } from './galaxyFolderScene.js';

/** Every long-lived ref GalaxyFolderView's nav/camera/event code shares —
 * one bundle so a click handler, the animation loop and this hook's own
 * effects all mutate the SAME instances. Mirrors the refs bundle the
 * original inline implementation built with a single `useMemo`. */
function useFolderRefsBundle(node, currentPath) {
  const canvasRef = useRef(null);
  const navRef = useRef(null);
  if (navRef.current === null) {
    navRef.current = { path: buildNavPath(node, currentPath) };
  }
  const savedFolderNavRef = useRef(null); // was module-level _savedFolderNav
  const savedFolderCamRef = useRef(null); // was module-level _savedFolderCam
  const camRef = useRef(savedFolderCamRef.current ? { ...savedFolderCamRef.current } : null);
  const animRef = useRef(null);
  const frameCount = useRef(0);
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

  const refs = useMemo(() => ({
    navRef, camRef, animRef, frameCount, sceneRef, nextSceneRef,
    zoomedFileRef, focusedFolderRef, zoomTargetRef, flyRef,
    prevNavRef, mouseRef, hoveredRef, tooltipRef, canvasRef, frameRef,
  }), []); // eslint-disable-line react-hooks/exhaustive-deps

  return { refs, savedFolderNavRef, savedFolderCamRef };
}

/** The current node + its scene, recomputed only when nav actually moves
 * (navVersion) or the scene cache misses (a different node than last built). */
function useCurrentSceneMemo(node, refs, navVersion) {
  const currentNode = useMemo(() => {
    const path = refs.navRef.current.path;
    return path[path.length - 1] || node;
  }, [node, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  const scene = useMemo(() => {
    if (!currentNode) { refs.sceneRef.current = null; return null; }
    if (refs.sceneRef.current && refs.sceneRef.current._node === currentNode) {
      return refs.sceneRef.current;
    }
    const s = buildFolderScene(currentNode, 800, 600);
    s._node = currentNode;
    refs.sceneRef.current = s;
    return s;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentNode]);

  return { currentNode, scene };
}

/** Reset nav (back to the project root) whenever `resetKey` changes — a
 * fresh mount of the same project, distinct from an external path sync. */
function useResetOnKeyChange(refs, node, resetKey, saveNav, savedFolderNavRef, savedFolderCamRef) {
  const prevResetKey = useRef(resetKey);
  useEffect(() => {
    if (resetKey !== prevResetKey.current) {
      prevResetKey.current = resetKey;
      refs.prevNavRef.current = null;
      refs.zoomedFileRef.current = null;
      refs.focusedFolderRef.current = null;
      refs.navRef.current = { path: [node] };
      savedFolderNavRef.current = null;
      savedFolderCamRef.current = null;
      refs.camRef.current = null;
      saveNav();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, node, saveNav]);
}

/**
 * Navigation state for GalaxyFolderView: the refs bundle, the current
 * node/scene, and the effects that keep them in sync with `currentPath`
 * (external navigation, e.g. the breadcrumb or explorer deep-links) and
 * `resetKey` (a fresh mount of the same project). `saveNav` commits the nav
 * ref + camera snapshot and bumps `navVersion` so dependents re-render;
 * `startTransition` arms the zoom/pan animation the camera hook advances.
 */
export function useGalaxyFolderNav({ node, currentPath, onPathChange, resetKey }) {
  const { refs, savedFolderNavRef, savedFolderCamRef } = useFolderRefsBundle(node, currentPath);
  const [navVersion, setNavVersion] = useState(0);
  const { currentNode, scene } = useCurrentSceneMemo(node, refs, navVersion);

  // Sync nav path when currentPath changes externally
  const prevSyncPath = useRef(currentPath);
  useEffect(() => {
    if (currentPath === prevSyncPath.current) return;
    prevSyncPath.current = currentPath;
    refs.navRef.current = { path: buildNavPath(node, currentPath) };
    savedFolderNavRef.current = null;
    savedFolderCamRef.current = null;
    refs.camRef.current = null;
    refs.sceneRef.current = null;
    refs.nextSceneRef.current = null;
    refs.flyRef.current = null;
    refs.zoomedFileRef.current = null;
    refs.focusedFolderRef.current = null;
    setNavVersion(v => v + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPath, node]);

  const saveNav = useCallback(() => {
    savedFolderNavRef.current = { ...refs.navRef.current, path: [...refs.navRef.current.path] };
    savedFolderCamRef.current = refs.camRef.current ? { ...refs.camRef.current } : null;
    setNavVersion(v => v + 1);
    const cur = refs.navRef.current.path[refs.navRef.current.path.length - 1];
    if (cur && onPathChange) onPathChange(cur.path || '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onPathChange]);

  const startTransition = useCallback((zoomingOut = false) => {
    const cam = refs.camRef.current;
    if (!cam) return;
    refs.animRef.current = { t: 0, sx: cam.x, sy: cam.y, sz: cam.z, out: zoomingOut };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useResetOnKeyChange(refs, node, resetKey, saveNav, savedFolderNavRef, savedFolderCamRef);

  return { refs, currentNode, scene, navVersion, setNavVersion, saveNav, startTransition };
}
