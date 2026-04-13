import { useRef, useEffect, useMemo, useCallback, useState } from 'react';
import {
  TAU, getThemeColors, invalidateThemeColors, scoreRGB, sevRGB, rgb, rgba,
  drawGlow, drawParticles,
  seedHash, seededRng, LEGEND_ITEMS,
} from '../core/galaxyCore.js';
import VizBreadcrumb from './VizBreadcrumb.jsx';

/* ── Position consistency engine ── */

function fingerprint(node) {
  const ch = node.children || [];
  return node.name + '|' + ch.map(c =>
    c.name + (c.violations || 0) + (c.isFile ? 'F' : 'D') + (c.complianceRate || 0).toFixed(1)
  ).join(':');
}

// Unwrap single-child folder chains that end in a file
function unwrapLeaf(node) {
  let n = node;
  while (!n.isFile && n.children && n.children.length === 1) {
    const only = n.children[0];
    if (only.isFile || !only.children || only.children.length === 0) {
      // Chain ends in a single file — treat as file, keep the file's name
      return only;
    }
    n = only;
  }
  return node;
}

function layoutChildren(node) {
  const ch = node.children || [];
  const resolved = ch.map(c => unwrapLeaf(c));
  const folders = resolved.filter(c => !c.isFile && c.children && c.children.length > 0);
  const files = resolved.filter(c => c.isFile || !c.children || c.children.length === 0);
  const all = [...folders, ...files];
  const rng = seededRng(seedHash(fingerprint(node)));
  return all.map(child => ({
    child,
    isFolder: folders.includes(child),
    angle: rng() * TAU,
    dist: rng(),
  }));
}

/* ── Scene builder ── */

function countDescendants(node) {
  if (!node.children) return 0;
  let n = node.children.length;
  for (const c of node.children) n += countDescendants(c);
  return n;
}

function buildFolderScene(node, W, H) {
  const positioned = layoutChildren(node);

  const rootStars = [];
  // Spread scales smoothly with child count — fewer objects stay closer
  const n = positioned.length;
  const baseFactor = 0.25 + Math.sqrt(n) * 0.2;
  const spread = Math.min(W, H) * baseFactor;

  positioned.forEach((ip, i) => {
    const c = ip.child;
    const total = (c.violations || 0) + (c.compliance || 0);
    const desc = ip.isFolder ? countDescendants(c) : 0;
    const radius = ip.isFolder
      ? 6 + Math.sqrt(Math.max(desc, 1)) * 1.2
      : 5 + Math.sqrt(c.violations || 1) * 1.2;
    const rate = c.complianceRate || 0;
    const sev = c.severity || { critical: 0, major: 0, minor: 0 };
    let col;
    col = scoreRGB(rate * 10);

    const distFactor = ip.isFolder ? (0.35 + ip.dist * 0.65) : (0.2 + ip.dist * 0.5);
    const dist = positioned.length === 1 ? 0 : spread * distFactor;
    const ox = Math.cos(ip.angle) * dist;
    const oy = Math.sin(ip.angle) * dist;

    let particles = [];
    if (ip.isFolder) {
      // Show severity alert particles for folders with violations in descendants
      if (sev.critical > 0 || sev.major > 0 || sev.minor > 0) {
        const fRng = seededRng(seedHash((c.path || c.name) + ':fsev'));
        const addAlert = (count, sevName) => {
          const sevCol = sevRGB(sevName);
          const n = Math.min(count, 3); // max 3 per severity — just alerts, not full count
          for (let j = 0; j < n; j++) {
            particles.push({
              col: sevCol, sev: sevName,
              or: radius * 1.5 + fRng() * radius * 1.0,
              os: (0.015 + fRng() * 0.03) * (fRng() > 0.5 ? 1 : -1),
              op: fRng() * TAU,
              sz: sevName === 'critical' ? 3.0 + fRng() * 0.7 : sevName === 'major' ? 2.3 + fRng() * 0.5 : 1.6 + fRng() * 0.4,
              ec: 0.7 + fRng() * 0.3,
              tp: fRng() * TAU,
            });
          }
        };
        if (sev.critical > 0) addAlert(sev.critical, 'critical');
        if (sev.major > 0) addAlert(sev.major, 'major');
        if (sev.minor > 0) addAlert(sev.minor, 'minor');
      }
    } else if (c.violations > 0) {
      // File particles: only for files with violations
      const rng2 = seededRng(seedHash((c.path || c.name) + ':fp'));
      const addP = (count, sevName) => {
        const col = sevRGB(sevName);
        for (let j = 0; j < Math.min(count, 10); j++) {
          particles.push({
            col, sev: sevName,
            or: radius * 1.2 + rng2() * radius * 1.5,
            os: (0.03 + rng2() * 0.07) * (rng2() > 0.5 ? 1 : -1),
            op: rng2() * TAU,
            sz: sevName === 'critical' ? 2.2 + rng2() * 0.5 : sevName === 'major' ? 1.8 + rng2() * 0.4 : 1.2 + rng2() * 0.3,
            ec: 0.65 + rng2() * 0.35,
            tp: rng2() * TAU,
          });
        }
      };
      addP(sev.critical || 0, 'critical');
      addP(sev.major || 0, 'major');
      addP(sev.minor || 0, 'minor');
    }

    rootStars.push({
      name: c.name,
      path: c.path,
      isFolder: ip.isFolder,
      violations: c.violations || 0,
      compliance: c.compliance || 0,
      complianceRate: rate,
      severity: sev,
      col, radius,
      ox, oy,
      pp: ip.angle,
      x: 0, y: 0,
      _node: c,
      particles,
    });
  });

  // Centroid correction
  if (rootStars.length > 0) {
    let cx = 0, cy = 0;
    rootStars.forEach(s => { cx += s.ox; cy += s.oy; });
    cx /= rootStars.length; cy /= rootStars.length;
    rootStars.forEach(s => { s.ox -= cx; s.oy -= cy; });
  }

  // Repulsion pass — push overlapping stars apart
  // Adaptively reduce iterations for large sets to keep O(n^2) bounded
  const folderGap = 10 + Math.min(n, 20) * 1.0;
  const fileGap = 1;
  const repulsionIters = rootStars.length > 50 ? 3 : rootStars.length > 20 ? 5 : 8;
  for (let iter = 0; iter < repulsionIters; iter++) {
    for (let i = 0; i < rootStars.length; i++) {
      for (let j = i + 1; j < rootStars.length; j++) {
        const a = rootStars[i], b = rootStars[j];
        const dx = b.ox - a.ox, dy = b.oy - a.oy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.1;
        // Tight gap between files, normal gap when a folder is involved
        const gap = (!a.isFolder && !b.isFolder) ? fileGap : folderGap;
        const minDist = a.radius + b.radius + gap;
        if (dist < minDist) {
          const push = (minDist - dist) / 2;
          const nx = dx / dist, ny = dy / dist;
          a.ox -= nx * push;
          a.oy -= ny * push;
          b.ox += nx * push;
          b.oy += ny * push;
        }
      }
    }
  }
  // Re-center after repulsion
  if (rootStars.length > 0) {
    let cx2 = 0, cy2 = 0;
    rootStars.forEach(s => { cx2 += s.ox; cy2 += s.oy; });
    cx2 /= rootStars.length; cy2 /= rootStars.length;
    rootStars.forEach(s => { s.ox -= cx2; s.oy -= cy2; });
  }

  // Normalize: if stars extend too far after repulsion, scale everything down to fit.
  // Target: all stars + their visual footprint within a circle of radius targetR.
  const targetR = Math.min(W, H) * 0.42;
  let _maxExtent = 0;
  rootStars.forEach(s => {
    const margin = s.particles.length > 0 ? s.radius * 3 : s.radius * 2;
    const ext = Math.max(Math.abs(s.ox) + margin, Math.abs(s.oy) + margin);
    if (ext > _maxExtent) _maxExtent = ext;
  });
  if (_maxExtent > targetR && _maxExtent > 0) {
    const scale = targetR / _maxExtent;
    rootStars.forEach(s => { s.ox *= scale; s.oy *= scale; });
    _maxExtent = targetR;
  }

  // Minimum spanning tree — connects ALL stars into one constellation
  const lines = [];
  if (rootStars.length >= 2) {
    const connected = new Set([0]);
    while (connected.size < rootStars.length) {
      let bestA = -1, bestB = -1, bestD = Infinity;
      for (const ai of connected) {
        for (let bi = 0; bi < rootStars.length; bi++) {
          if (connected.has(bi)) continue;
          const dx = rootStars[ai].ox - rootStars[bi].ox;
          const dy = rootStars[ai].oy - rootStars[bi].oy;
          const d = dx * dx + dy * dy;
          if (d < bestD) { bestD = d; bestA = ai; bestB = bi; }
        }
      }
      if (bestB >= 0) {
        lines.push({ a: bestA, b: bestB });
        connected.add(bestB);
      } else break;
    }
  }

  // Background
  const bg = Array.from({ length: 120 }, () => ({
    x: Math.random(), y: Math.random(),
    sz: Math.random() * 1.2,
    tw: Math.random() * TAU,
    sp: 0.3 + Math.random() * 0.7,
  }));

  return { rootStars, lines, bg, _maxExtent };
}

/* ── Module-level saved state ── */
let _savedFolderNav = null;
let _savedFolderCam = null;

/* ── Component ── */

function buildNavPath(root, targetPath) {
  const path = [root];
  if (targetPath) {
    let cur = root;
    while (cur && cur.path !== targetPath) {
      const child = (cur.children || []).find(c => targetPath === c.path || targetPath.startsWith(c.path + '/'));
      if (!child) break;
      path.push(child);
      cur = child;
    }
  }
  return path;
}

export default function GalaxyFolderView({ node, currentPath = '', onPathChange, onFileClick, onNavigate, showLabels = true, setShowLabels, darkMode, resetKey = 0, projectName = '' }) {
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  // Invalidate cached theme colors when dark mode toggles
  useEffect(() => { invalidateThemeColors(); }, [darkMode]);

  // Navigation: path is an array of node references.
  // Initialize from currentPath so we start at the correct depth on mount.
  const navRef = useRef(null);
  if (navRef.current === null) {
    navRef.current = { path: buildNavPath(node, currentPath) };
  }
  const camRef = useRef(_savedFolderCam ? { ..._savedFolderCam } : null);
  const animRef = useRef(null);
  const frameCount = useRef(0);
  const [navVersion, setNavVersion] = useState(0);
  const timeRef = useRef(0);
  const mouseRef = useRef({ x: -1, y: -1 });
  const hoveredRef = useRef(null);
  const tooltipRef = useRef(null);
  const frameRef = useRef(null);
  const prevNavRef = useRef(null);
  const zoomedFileRef = useRef(null); // non-null when zoomed into a file star
  const focusedFolderRef = useRef(null); // non-null when zoomed onto a folder star (preview mode)
  const zoomTargetRef = useRef(null); // {x, y, z} for background click zoom
  const flyRef = useRef(null); // fly-into-star transition state

  const TRANS = 0.8;
  const FLY_DURATION = 1.4; // total fly transition seconds

  // Current node is last in path
  const currentNode = useMemo(() => {
    const path = navRef.current.path;
    return path[path.length - 1] || node;
  }, [node, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build scene from current node — reuse preloaded scene if already set by fly transition
  const sceneRef = useRef(null);
  const nextSceneRef = useRef(null);
  const scene = useMemo(() => {
    if (!currentNode) { sceneRef.current = null; return null; }
    // If sceneRef already has a scene for this node (set by fly transition), reuse it
    if (sceneRef.current && sceneRef.current._node === currentNode) {
      return sceneRef.current;
    }
    const s = buildFolderScene(currentNode, 800, 600);
    s._node = currentNode;
    sceneRef.current = s;
    return s;
  }, [currentNode]);

  // Sync nav path when currentPath changes externally (after mount)
  const prevSyncPath = useRef(currentPath);
  useEffect(() => {
    if (currentPath === prevSyncPath.current) return;
    prevSyncPath.current = currentPath;
    navRef.current = { path: buildNavPath(node, currentPath) };
    _savedFolderNav = null;
    _savedFolderCam = null;
    camRef.current = null;
    sceneRef.current = null;
    nextSceneRef.current = null;
    flyRef.current = null;
    zoomedFileRef.current = null;
    focusedFolderRef.current = null;
    setNavVersion(v => v + 1);
  }, [currentPath, node]);

  const saveNav = useCallback(() => {
    _savedFolderNav = { ...navRef.current, path: [...navRef.current.path] };
    _savedFolderCam = camRef.current ? { ...camRef.current } : null;
    setNavVersion(v => v + 1);
    // Sync path back to parent for cross-view navigation
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
      _savedFolderNav = null;
      _savedFolderCam = null;
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

  // World-to-screen
  const w2s = useCallback((wx, wy) => {
    const cam = camRef.current;
    if (!cam) return { x: wx, y: wy };
    return { x: (wx - cam.x) * cam.z + size.w / 2, y: (wy - cam.y) * cam.z + size.h / 2 };
  }, [size.w, size.h]);

  // Compute fitZoom from scene extent and actual screen size
  const getFitZoom = useCallback((s) => {
    const ext = s?._maxExtent;
    if (!ext || ext <= 0) return 1;
    const halfView = Math.min(size.w, size.h) / 2 * 0.85; // 15% breathing room
    return Math.min(halfView / ext, 4);
  }, [size.w, size.h]);

  // Camera target — computeFocusCamera
  const computeFocusCamera = useCallback(() => {
    const fz = getFitZoom(sceneRef.current);
    const zf = zoomedFileRef.current;
    if (zf) return { x: zf.x, y: zf.y, z: Math.max(6, fz * 4) };
    const zt = zoomTargetRef.current;
    if (zt) return { x: zt.x, y: zt.y, z: zt.z };
    const ff = focusedFolderRef.current;
    if (ff) {
      // Zoom so the folder's preview circle fills ~60% of screen
      const star = (sceneRef.current || scene)?.rootStars?.[ff.starIdx];
      const previewR = star ? star.radius * 4 : 30; // matches rendering previewR = sr * 4 at z=1
      const targetScreenR = Math.min(size.w, size.h) * 0.3;
      const focusZ = targetScreenR / (previewR * 0.5);
      return { x: ff.x, y: ff.y, z: Math.max(fz * 2, focusZ) };
    }
    return { x: size.w / 2, y: size.h / 2, z: fz };
  }, [size.w, size.h, getFitZoom]);

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

      // --- Fly-into-star transition ---
      const fly = flyRef.current;
      let sceneAlpha = 1;
      let bloomAlpha = 0;

      if (fly) {
        fly.t = Math.min(1, fly.t + 0.016 / FLY_DURATION);
        // Smooth ease in-out
        const gt = fly.t;
        const ease = gt < 0.5 ? 2 * gt * gt : 1 - Math.pow(-2 * gt + 2, 2) / 2;

        if (!fly._targetFz) {
          fly._targetFz = getFitZoom(nextSceneRef.current);
        }
        const tFz = fly._targetFz || 1;

        if (fly.reverse) {
          // --- FLY-OUT (back navigation) ---
          // Crossfade at 40% — swap scene while both are partially visible
          const swapAt = 0.4;
          if (gt < swapAt) {
            // Current scene shrinks
            const p = gt / swapAt;
            cam.z = fly.sz * (1 - p * 0.7); // z shrinks to 30% of original
            sceneAlpha = 1 - p * 0.8; // fade to 20%
          }
          if (gt >= swapAt && !fly.swapped) {
            fly.swapped = true;
            zoomedFileRef.current = null;
            focusedFolderRef.current = null;
            navRef.current = { path: [...fly.newPath] };
            sceneRef.current = nextSceneRef.current;
            sceneRef.current._node = fly.newPath[fly.newPath.length - 1];
            nextSceneRef.current = null;
            frameCount.current = 0;
            cam.x = W / 2; cam.y = H / 2; cam.z = tFz * 6;
            saveNav();
          }
          if (gt >= swapAt) {
            const p = (gt - swapAt) / (1 - swapAt);
            const pe = 1 - (1 - p) * (1 - p);
            cam.z = tFz * 6 + (tFz - tFz * 6) * pe; // z: 6x → 1x fitZoom
            sceneAlpha = 0;
            bloomAlpha = 0.2 + 0.8 * pe;
          }
        } else {
          // --- FLY-IN (enter folder) ---
          // Smooth approach: zoom gently into the star, then expand new scene
          const swapAt = 0.35;
          if (gt < swapAt) {
            const p = gt / swapAt;
            const pe = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2; // ease in-out
            cam.x = fly.sx + (fly.starX - fly.sx) * pe;
            cam.y = fly.sy + (fly.starY - fly.sy) * pe;
            cam.z = fly.sz + (fly.sz * 4 - fly.sz) * pe; // gentle zoom to 4x
            sceneAlpha = 1 - pe * 0.85;
          }
          if (gt >= swapAt && !fly.swapped) {
            fly.swapped = true;
            zoomedFileRef.current = null;
            navRef.current = { path: [...fly.newPath] };
            sceneRef.current = nextSceneRef.current;
            sceneRef.current._node = fly.targetNode || fly.newPath[fly.newPath.length - 1];
            nextSceneRef.current = null;
            frameCount.current = 0;
            cam.x = W / 2; cam.y = H / 2; cam.z = tFz * 0.3;
            saveNav();
          }
          if (gt >= swapAt) {
            const p = (gt - swapAt) / (1 - swapAt);
            const pe = 1 - Math.pow(1 - p, 3); // ease-out cubic — slow landing
            cam.z = tFz * 0.3 + (tFz - tFz * 0.3) * pe; // z: 30% → 100% fitZoom
            sceneAlpha = 0;
            bloomAlpha = 0.15 + 0.85 * pe;
          }
        }

        if (fly.t >= 1) {
          flyRef.current = null;
          const endFz = getFitZoom(sceneRef.current);
          cam.x = W / 2; cam.y = H / 2; cam.z = endFz;
          setNavVersion(v => v + 1);
        }
      }

      // --- Camera (normal, non-fly) ---
      // Re-read flyRef — auto-enter may have set it during previous anim completion
      if (!flyRef.current) {
        const tg = computeFocusCamera();
        const anim = animRef.current;
        frameCount.current++;
        if (!anim && frameCount.current <= 3) {
          cam.x = tg.x; cam.y = tg.y; cam.z = tg.z;
        } else if (!anim) {
          cam.x += (tg.x - cam.x) * 0.08;
          cam.y += (tg.y - cam.y) * 0.08;
          cam.z += (tg.z - cam.z) * 0.08;
        } else {
          anim.t = Math.min(1, anim.t + 0.016 / TRANS);
          const ease = anim.t < 0.5 ? 4 * anim.t * anim.t * anim.t : 1 - Math.pow(-2 * anim.t + 2, 3) / 2;
          const lag = Math.pow(anim.t, 0.7); const lagE = lag * lag * (3 - 2 * lag);
          const posE = anim.out ? ease : lagE;
          const zoomE = anim.out ? lagE : ease;
          cam.x = anim.sx + (tg.x - anim.sx) * posE;
          cam.y = anim.sy + (tg.y - anim.sy) * posE;
          cam.z = anim.sz + (tg.z - anim.sz) * zoomE;
          if (anim.t >= 1) {
            animRef.current = null; prevNavRef.current = null;
            // Auto-enter focused folder after zoom completes
            const ff3 = focusedFolderRef.current;
            if (ff3 && ff3.autoEnter && !flyRef.current) {
              const curScene = sceneRef.current || scene;
              const star = curScene.rootStars[ff3.starIdx];
              if (star && star.isFolder) {
                nextSceneRef.current = buildFolderScene(star._node, 800, 600);
                nextSceneRef.current._node = star._node;
                flyRef.current = {
                  t: 0,
                  starX: star.x, starY: star.y,
                  starCol: star.col,
                  dimStarIdx: ff3.starIdx,
                  sx: cam.x, sy: cam.y, sz: cam.z,
                  targetNode: star._node,
                  newPath: [...navRef.current.path, star._node],
                  swapped: false,
                };
                focusedFolderRef.current = null;
              }
            }
          }
        }
      }

      // Use the live scene ref (may have been swapped during fly)
      const activeScene = sceneRef.current || scene;

      // Recompute star world positions for active scene
      activeScene.rootStars.forEach((s, i) => {
        const drift = Math.sin(t * 0.015 + i * 1.1) * 2;
        s.x = W / 2 + s.ox + drift;
        s.y = H / 2 + s.oy + Math.cos(t * 0.012 + i * 0.8) * 2;
      });
      // Track focused folder/file position as star drifts
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

      // --- Draw ---
      const tc = getThemeColors(canvasRef.current?.parentElement);
      const grad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.6);
      grad.addColorStop(0, tc.bgAlt); grad.addColorStop(1, tc.bg);
      ctx.fillStyle = grad; ctx.fillRect(0, 0, W, H);

      // Scene opacity (fade out during fly approach)
      const activeFly = flyRef.current;
      // If fly was just started mid-frame (t=0, sceneAlpha still 1), begin fade immediately
      const effectiveAlpha = activeFly
        ? (activeFly.swapped ? bloomAlpha : (activeFly.t === 0 ? 0.85 : sceneAlpha))
        : 1;
      if (effectiveAlpha < 0.01) {
        // Scene fully faded, skip drawing stars
        frameRef.current = requestAnimationFrame(frame);
        return;
      }
      ctx.globalAlpha = effectiveAlpha;

      // Background nebula — represents overall folder score
      const curNode = navRef.current.path[navRef.current.path.length - 1];
      if (curNode) {
        const nbCol = scoreRGB((curNode.complianceRate || 0) * 10);
        const { r: nr, g: ng, b: nb } = nbCol;
        const nbR = Math.max(W, H) * 0.7;
        const nbGrad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, nbR);
        nbGrad.addColorStop(0, `rgba(${nr},${ng},${nb},0.015)`);
        nbGrad.addColorStop(0.5, `rgba(${nr},${ng},${nb},0.007)`);
        nbGrad.addColorStop(1, `rgba(${nr},${ng},${nb},0)`);
        ctx.beginPath(); ctx.arc(W / 2, H / 2, nbR, 0, TAU);
        ctx.fillStyle = nbGrad; ctx.fill();
        for (let bi = 0; bi < 4; bi++) {
          const ba = t * 0.005 + bi * TAU / 4;
          const bx = W / 2 + Math.cos(ba) * nbR * 0.35;
          const by = H / 2 + Math.sin(ba) * nbR * 0.35;
          const br = nbR * (0.3 + 0.08 * Math.sin(t * 0.015 + bi * 1.7));
          const blGrad = ctx.createRadialGradient(bx, by, 0, bx, by, br);
          blGrad.addColorStop(0, `rgba(${nr},${ng},${nb},0.008)`);
          blGrad.addColorStop(1, `rgba(${nr},${ng},${nb},0)`);
          ctx.beginPath(); ctx.arc(bx, by, br, 0, TAU);
          ctx.fillStyle = blGrad; ctx.fill();
        }
      }

      // Background starfield
      const { r: mr, g: mg, b: mb } = tc.textMuted;
      activeScene.bg.forEach(s => {
        const a = 0.15 + 0.15 * Math.sin(t * s.sp + s.tw);
        ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.sz, 0, TAU);
        ctx.fillStyle = `rgba(${mr},${mg},${mb},${a})`; ctx.fill();
      });

      // --- Draw constellation lines ---
      const mx = mouseRef.current.x, my = mouseRef.current.y;
      let newHovered = null;

      activeScene.lines.forEach(l => {
        const sa = w2s(activeScene.rootStars[l.a].x, activeScene.rootStars[l.a].y);
        const sb = w2s(activeScene.rootStars[l.b].x, activeScene.rootStars[l.b].y);
        ctx.beginPath(); ctx.moveTo(sa.x, sa.y); ctx.lineTo(sb.x, sb.y);
        ctx.strokeStyle = `rgba(${mr},${mg},${mb},0.25)`;
        ctx.lineWidth = 0.8; ctx.stroke();
      });

      // --- Draw stars ---
      const pendingLabels = [];
      activeScene.rootStars.forEach((s, i) => {
        const sc = w2s(s.x, s.y);
        const pulse = 1 + 0.01 * Math.sin(t * 0.4 + s.pp);
        const sr = s.radius * pulse * cam.z * 0.5;

        // Read flyRef.current directly — may have been set mid-frame by auto-enter
        const curFly = flyRef.current;
        const isFocusedFolder = s.isFolder && (
          (focusedFolderRef.current && focusedFolderRef.current.starIdx === i) ||
          (curFly && !curFly.reverse && !curFly.swapped && curFly.dimStarIdx === i)
        );
        // Star dims progressively as it gets bigger on screen (closer camera)
        // sr is the screen-space radius — larger means closer
        const dimThreshold = 30; // start dimming when star is 30px on screen
        const starAlpha = s.isFolder && sr > dimThreshold
          ? Math.max(0.15, 1 - (sr - dimThreshold) / 80)
          : 1;
        drawGlow(ctx, sc.x, sc.y, sr, s.col, starAlpha);

        // Folder stars: nebula + cluster detail
        // During fly approach: fade out nebula; during focus: keep it visible
        if (s.isFolder) {
          const { r: cr, g: cg, b: cb } = s.col;
          const zoomed = cam.z > 2;
          // Nebula: visible during focus, fades smoothly during fly-in
          const isFlying = curFly && !curFly.reverse && !curFly.swapped && curFly.dimStarIdx === i;
          const nebulaFade = isFlying ? Math.max(0, 1 - (curFly.t / 0.35)) : 1;

          // Nebula — always visible, intensifies when zoomed
          const nebulaR = zoomed
            ? (s.radius + 40) * cam.z * 0.4
            : sr * 5;
          const nebulaA = (zoomed ? Math.min(1, (cam.z - 2) / 3) * 0.35 : 0.08) * nebulaFade;
          const nebulaGrad = ctx.createRadialGradient(sc.x, sc.y, 0, sc.x, sc.y, nebulaR);
          nebulaGrad.addColorStop(0, `rgba(${cr},${cg},${cb},${nebulaA})`);
          nebulaGrad.addColorStop(0.5, `rgba(${cr},${cg},${cb},${nebulaA * 0.5})`);
          nebulaGrad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
          ctx.beginPath(); ctx.arc(sc.x, sc.y, nebulaR, 0, TAU);
          ctx.fillStyle = nebulaGrad; ctx.fill();

          // Animated texture blobs — always, subtle at normal zoom
          const blobA = (zoomed ? Math.min(0.18, (cam.z - 2) / 15) : 0.025) * nebulaFade;
          for (let bi = 0; bi < 3; bi++) {
            const ba = t * 0.01 + bi * TAU / 3;
            const bx = sc.x + Math.cos(ba) * nebulaR * 0.3;
            const by = sc.y + Math.sin(ba) * nebulaR * 0.3;
            const br = nebulaR * (0.4 + 0.1 * Math.sin(t * 0.02 + bi * 2));
            const blobGrad = ctx.createRadialGradient(bx, by, 0, bx, by, br);
            blobGrad.addColorStop(0, `rgba(${cr},${cg},${cb},${blobA})`);
            blobGrad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
            ctx.beginPath(); ctx.arc(bx, by, br, 0, TAU);
            ctx.fillStyle = blobGrad; ctx.fill();
          }

          // Dashed circle border
          const borderR = sr * 3.5;
          ctx.beginPath(); ctx.arc(sc.x, sc.y, borderR, 0, TAU);
          ctx.strokeStyle = `rgba(${cr},${cg},${cb},${0.1 * nebulaFade})`;
          ctx.lineWidth = 1;
          ctx.setLineDash([6, 12]); ctx.stroke(); ctx.setLineDash([]);
          s._clusterHitR = borderR;

          if (!zoomed) {
            // Normal zoom: also show double-ring halo
            ctx.beginPath(); ctx.arc(sc.x, sc.y, sr * 2.2, 0, TAU);
            ctx.strokeStyle = rgba(s.col, 0.12); ctx.lineWidth = 0.8; ctx.stroke();
          }
        }

        // File particles only (folders use inner constellation instead)
        if (s.particles.length > 0) {
          const pScale = cam.z * 0.5;
          drawParticles(ctx, sc.x, sc.y, s.particles, pScale, 0.8, t, pScale);
        }

        // At cam.z > 2.5: file violation particles as labeled orbs
        if (!s.isFolder && cam.z > 2.5 && s.particles.length > 0) {
          const vAlpha = Math.min(1, (cam.z - 2.5) / 2);
          const vScale = cam.z * 0.06;
          s.particles.forEach(p => {
            const a = t * p.os + p.op;
            const px = sc.x + Math.cos(a) * p.or * p.ec * vScale;
            const py = sc.y + Math.sin(a) * p.or * vScale;
            const tw = 0.5 + 0.06 * Math.sin(t * 0.4 + p.tp);
            const psr = p.sz * vScale * 0.5;
            if (psr > 1.5) {
              drawGlow(ctx, px, py, psr, p.col, vAlpha * tw);
              if (showLabels && psr > 3) {
                const sevName = p.sev.charAt(0).toUpperCase() + p.sev.slice(1);
                ctx.font = `500 ${Math.max(7, Math.min(11, psr * 0.8))}px -apple-system,BlinkMacSystemFont,sans-serif`;
                ctx.textAlign = 'center'; ctx.fillStyle = rgba(p.col, 0.85 * vAlpha);
                ctx.fillText(sevName, px, py - psr - 4);
              }
            }
          });
        }

        // Collect label info for deferred collision-aware drawing
        if (showLabels && sr > 1) {
          const fs = Math.min(cam.z, 1.5);
          const shortName = s.name.includes('/') ? s.name.split('/')[0] : s.name;
          const label = s.isFolder ? shortName : s.name;
          const fontSize = Math.max(9, 11 * fs);
          const lw = label.length * fontSize * 0.55;
          const lh = fontSize + 4;
          const lx = sc.x;
          const ly = sc.y - sr - 14 * fs;
          const importance = (s.isFolder ? 1000 : 0) + (s.violations || 0) + (s.radius || 0);
          pendingLabels.push({ s, sc, sr, fs, label, fontSize, lx, ly, lw, lh, importance, col: s.col });
        }

        // Hit testing — when zoomed, the entire cluster area is clickable
        if (!animRef.current && !fly && mx >= 0) {
          const dx = mx - sc.x, dy = my - sc.y;
          const d2 = dx * dx + dy * dy;
          const clusterR = s.isFolder && s._clusterHitR > 0 ? s._clusterHitR : 0;
          const starHitR = Math.max(sr * 2, 14);
          if (d2 < starHitR * starHitR || (clusterR > 0 && d2 < clusterR * clusterR)) {
            newHovered = { type: s.isFolder ? 'folder' : 'file', starIdx: i, data: s };
          }
        }
      });

      // Draw labels with collision avoidance — most important first
      pendingLabels.sort((a, b) => b.importance - a.importance);
      const placedLabels = [];
      pendingLabels.forEach(lb => {
        const halfW = lb.lw / 2, halfH = lb.lh / 2;
        const collides = placedLabels.some(pl => {
          return Math.abs(lb.lx - pl.lx) < (halfW + pl.lw / 2 + 4) &&
                 Math.abs(lb.ly - pl.ly) < (halfH + pl.lh / 2 + 2);
        });
        if (collides) return;
        placedLabels.push(lb);
        ctx.font = `500 ${lb.fontSize}px -apple-system,BlinkMacSystemFont,sans-serif`;
        ctx.textAlign = 'center';
        ctx.fillStyle = rgba(tc.text, 0.6);
        ctx.fillText(lb.label, lb.lx, lb.ly);
        if (lb.s.violations > 0) {
          ctx.font = `${Math.max(7, 9 * lb.fs)}px -apple-system,BlinkMacSystemFont,sans-serif`;
          ctx.fillStyle = rgba(tc.textMuted, 0.6);
          ctx.fillText(lb.s.violations + ' viol.', lb.sc.x, lb.sc.y + lb.sr + 12 * lb.fs);
        } else if (lb.s.isFolder) {
          ctx.font = `${Math.max(7, 9 * lb.fs)}px -apple-system,BlinkMacSystemFont,sans-serif`;
          ctx.fillStyle = rgba(tc.textMuted, 0.5);
          ctx.fillText((lb.s.complianceRate * 100).toFixed(0) + '%', lb.sc.x, lb.sc.y + lb.sr + 12 * lb.fs);
        }
      });

      ctx.globalAlpha = 1;
      hoveredRef.current = newHovered;
      frameRef.current = requestAnimationFrame(frame);
    }

    frameRef.current = requestAnimationFrame(frame);
    return () => { running = false; cancelAnimationFrame(frameRef.current); };
  }, [scene, size, showLabels, w2s, computeFocusCamera, getFitZoom]);

  // --- Navigation ---
  const navigateTo = useCallback((newPath) => {
    if (animRef.current) return;
    const oldLen = navRef.current.path.length;
    const zoomingOut = newPath.length < oldLen;
    if (zoomingOut) prevNavRef.current = { ...navRef.current, path: [...navRef.current.path] };
    zoomedFileRef.current = null;
    focusedFolderRef.current = null;
    navRef.current = { path: [...newPath] };
    frameCount.current = 0;
    startTransition(zoomingOut);
    saveNav();
  }, [saveNav, startTransition]);

  // --- Mouse + click handlers ---
  const handleMouseMove = useCallback((e) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const h = hoveredRef.current;
    canvasRef.current.style.cursor = h ? 'pointer' : 'default';
    updateTooltip(e.clientX, e.clientY);
  }, []);

  const handleMouseLeave = useCallback(() => {
    mouseRef.current = { x: -1, y: -1 };
    hoveredRef.current = null;
    if (tooltipRef.current) tooltipRef.current.style.display = 'none';
  }, []);

  const handleClick = useCallback(() => {
    if (animRef.current || flyRef.current) return;
    const nav = navRef.current;
    const h = hoveredRef.current;

    if (h) {
      if (h.type === 'folder') {
        const s = h.data;
        const ff = focusedFolderRef.current;
        if (ff && ff.starIdx === h.starIdx) {
          // Already focused — ignore double clicks, auto-enter handles it
          return;
        } else {
          // Single click → zoom to preview, then auto-enter when zoom finishes
          zoomedFileRef.current = null;
          zoomTargetRef.current = null;
          focusedFolderRef.current = { x: s.x, y: s.y, starIdx: h.starIdx, data: s, autoEnter: true };
          startTransition(false);
          saveNav();
        }
        return;
      }
      if (h.type === 'file') {
        // Click file star: zoom to z=6
        const s = h.data;
        focusedFolderRef.current = null;
        zoomTargetRef.current = null;
        zoomedFileRef.current = { x: s.x, y: s.y, starIdx: h.starIdx, data: s };
        startTransition(false);
        saveNav();
        return;
      }
    }

    // Click empty space
    if (zoomedFileRef.current) {
      zoomedFileRef.current = null;
      zoomTargetRef.current = null;
      startTransition(true);
      saveNav();
    } else if (zoomTargetRef.current) {
      zoomTargetRef.current = null;
      startTransition(true);
      saveNav();
    } else if (focusedFolderRef.current) {
      focusedFolderRef.current = null;
      startTransition(true);
      saveNav();
    } else if (nav.path.length <= 1) {
      // Root level: zoom toward click position — find nearest star and zoom toward it
      const cam = camRef.current;
      if (cam && mouseRef.current.x >= 0) {
        const wx = (mouseRef.current.x - size.w / 2) / cam.z + cam.x;
        const wy = (mouseRef.current.y - size.h / 2) / cam.z + cam.y;
        // Find nearest star to click
        const curScene = sceneRef.current || scene;
        let nearestStar = null, nearestD = Infinity;
        if (curScene) {
          curScene.rootStars.forEach(s => {
            const dx = s.x - wx, dy = s.y - wy;
            const d = dx * dx + dy * dy;
            if (d < nearestD) { nearestD = d; nearestStar = s; }
          });
        }
        // Target: blend between click pos and nearest star (pull toward star)
        const tx = nearestStar ? wx * 0.3 + nearestStar.x * 0.7 : wx;
        const ty = nearestStar ? wy * 0.3 + nearestStar.y * 0.7 : wy;
        const newZ = cam.z * 2.5;
        const maxZ = getFitZoom(curScene) * 10;
        zoomTargetRef.current = { x: tx, y: ty, z: Math.min(newZ, maxZ) };
        startTransition(false);
        saveNav();
      }
    } else if (nav.path.length > 1) {
      if (flyRef.current) return;
      const cam = camRef.current;
      const parentPath = nav.path.slice(0, -1);
      const parentNode = parentPath[parentPath.length - 1];
      nextSceneRef.current = buildFolderScene(parentNode, 800, 600);
      flyRef.current = {
        t: 0, reverse: true,
        sx: cam.x, sy: cam.y, sz: cam.z,
        newPath: parentPath,
        starCol: getThemeColors().gradeMid,
        swapped: false,
      };
    }
  }, [navigateTo, startTransition, saveNav]);

  const goToPathIndex = useCallback((idx) => {
    if (idx >= navRef.current.path.length - 1 || flyRef.current) return;
    const newPath = navRef.current.path.slice(0, idx + 1);
    const targetNode = newPath[newPath.length - 1];
    const cam = camRef.current;
    nextSceneRef.current = buildFolderScene(targetNode, 800, 600);
    flyRef.current = {
      t: 0, reverse: true,
      sx: cam.x, sy: cam.y, sz: cam.z,
      newPath,
      starCol: getThemeColors().gradeMid,
      swapped: false,
    };
  }, []);

  // Tooltip updater
  const updateTooltip = useCallback((cx, cy) => {
    const el = tooltipRef.current;
    if (!el) return;
    const h = hoveredRef.current;
    if (!h || animRef.current) { el.style.display = 'none'; return; }
    const d = h.data;
    const row = (label, value, color) => `<div style="display:flex;justify-content:space-between;gap:12px;color:${color || 'var(--color-text-muted)'}"><span>${label}</span><span style="color:${color || 'var(--color-text)'};font-weight:500">${value}</span></div>`;
    const rows = [];
    const sev = d.severity || {};
    if (h.type === 'folder') {
      rows.push(row('Compliance', (d.complianceRate * 100).toFixed(0) + '%'));
      rows.push(row('Violations', d.violations));
      rows.push(row('Contents', countDescendants(d._node)));
    } else {
      rows.push(row('Violations', d.violations));
      rows.push(row('Compliance', d.compliance));
    }
    if (d.violations > 0) {
      if (sev.critical) rows.push(row('Critical', sev.critical, 'var(--color-sev-critical-text)'));
      if (sev.major) rows.push(row('Major', sev.major, 'var(--color-sev-major-text)'));
      if (sev.minor) rows.push(row('Minor', sev.minor, 'var(--color-sev-minor-text)'));
    }
    const nameCol = rgb(d.col);
    const name = d.name;
    const ff = focusedFolderRef.current;
    const isFocused = h.type === 'folder' && ff && ff.starIdx === h.starIdx;
    const action = h.type === 'file' ? 'zoom in' : isFocused ? 'enter folder' : 'focus';
    el.innerHTML = `<div style="font-weight:600;color:${nameCol};margin-bottom:4px">${name}</div>${rows.join('')}<div style="margin-top:6px;color:var(--color-text-muted);font-size:11px;opacity:0.6">Click to ${action}</div>`;
    el.style.display = 'block';
    el.style.left = Math.min(cx + 16, window.innerWidth - 200) + 'px';
    el.style.top = Math.min(cy + 16, window.innerHeight - 160) + 'px';
  }, []);

  // Breadcrumb builder
  const breadcrumb = useMemo(() => {
    const path = navRef.current.path;
    const parts = [];
    parts.push({ label: projectName || 'Project', idx: 0 });
    for (let i = 1; i < path.length; i++) {
      parts.push({ label: path[i].name, idx: i });
    }
    return parts;
  }, [projectName, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Level info — shows zoomed file detail when a file is focused
  const levelInfo = useMemo(() => {
    if (!scene) return null;
    const zf = zoomedFileRef.current;
    if (zf && zf.data) {
      const s = zf.data;
      const sev = s.severity || {};
      return {
        title: s.name,
        lines: [
          { label: 'Violations', value: s.violations },
          { label: 'Compliance', value: s.compliance },
          ...(sev.critical ? [{ label: 'Critical', value: sev.critical }] : []),
          ...(sev.major ? [{ label: 'Major', value: sev.major }] : []),
          ...(sev.minor ? [{ label: 'Minor', value: sev.minor }] : []),
        ],
        hint: null,
        detailAction: () => { if (onFileClick) onFileClick(s._node); },
      };
    }
    const cn = currentNode;
    const folderCount = scene.rootStars.filter(s => s.isFolder).length;
    const fileCount = scene.rootStars.filter(s => !s.isFolder).length;
    const rate = cn.complianceRate;
    const cnSev = cn.severity || {};
    const isRoot = navRef.current.path.length <= 1;
    const lines = [
      { label: 'Compliance', value: (rate * 100).toFixed(0) + '%' },
      { label: 'Contents', value: folderCount + fileCount },
      { label: 'Violations', value: cn.violations },
    ];
    if (cn.violations > 0) {
      if (cnSev.critical > 0) lines.push({ label: 'Critical', value: cnSev.critical, color: 'var(--color-sev-critical-text)' });
      if (cnSev.major > 0) lines.push({ label: 'Major', value: cnSev.major, color: 'var(--color-sev-major-text)' });
      if (cnSev.minor > 0) lines.push({ label: 'Minor', value: cnSev.minor, color: 'var(--color-sev-minor-text)' });
    }
    return {
      title: isRoot ? (projectName || 'Project') : cn.name,
      lines,
      hint: folderCount > 0 ? 'Click a folder to zoom in, click again to enter' : null,
      detailAction: !isRoot ? () => {
        if (onFileClick) onFileClick(cn);
      } : null,
    };
  }, [scene, currentNode, projectName, onFileClick, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fade in
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (scene) setVisible(true);
  }, [scene]);

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
      />
      {/* Breadcrumb */}
      <VizBreadcrumb items={breadcrumb.map((bc, i) => ({
        label: bc.label,
        onClick: i < breadcrumb.length - 1 ? () => goToPathIndex(bc.idx) : undefined,
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
      {levelInfo && (
        <div style={{ position: 'absolute', top: 12, right: 16, background: 'color-mix(in srgb, var(--color-surface) 88%, transparent)', border: '1px solid var(--color-border)', borderRadius: 10, padding: '12px 18px', fontSize: 12, zIndex: 2, backdropFilter: 'blur(8px)', minWidth: 160 }}>
          <div style={{ fontWeight: 600, color: 'var(--color-text)', marginBottom: 8, fontSize: 13 }}>{levelInfo.title}</div>
          {levelInfo.lines.map((l, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, margin: '3px 0', color: l.color || 'var(--color-text-muted)' }}>
              <span>{l.label}</span>
              <span style={{ color: l.color || 'var(--color-text)', fontWeight: 500 }}>{l.value}</span>
            </div>
          ))}
          {levelInfo.hint && (
            <div style={{ marginTop: 8, color: 'var(--color-text-muted)', fontSize: 11, fontStyle: 'italic', opacity: 0.6 }}>{levelInfo.hint}</div>
          )}
          {levelInfo.detailAction && (
            <button
              type="button"
              onClick={levelInfo.detailAction}
              style={{ marginTop: 10, width: '100%', padding: '6px 12px', background: 'color-mix(in srgb, var(--color-accent) 20%, transparent)', border: '1px solid var(--color-border)', borderRadius: 6, color: 'var(--color-text)', fontSize: 11, cursor: 'pointer', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 35%, transparent)'; }}
              onMouseLeave={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 20%, transparent)'; }}
            >View Details</button>
          )}
        </div>
      )}
    </div>
  );
}
