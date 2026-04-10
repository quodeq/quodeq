import { useRef, useEffect, useMemo, useCallback, useState } from 'react';
import {
  TAU, getThemeColors, scoreRGB, sevRGB, rgb, rgba,
  drawGlow, drawParticles, mkParticles,
  seedHash, seededRng, gradeToScore, LEGEND_ITEMS,
} from '../core/galaxyCore.js';

/** Group violations and compliance by principle name, returning { [principleName]: { violations, compliance } } */
function groupByPrinciple(dim) {
  const groups = {};
  for (const v of (dim.violations || [])) {
    const key = v.principle || '(ungrouped)';
    if (!groups[key]) groups[key] = { violations: [], compliance: [] };
    groups[key].violations.push(v);
  }
  for (const c of (dim.compliance || [])) {
    const key = c.principle || '(ungrouped)';
    if (!groups[key]) groups[key] = { violations: [], compliance: [] };
    groups[key].compliance.push(c);
  }
  return groups;
}

/** Build a lookup from principle name to { grade, score } from dim.principles array */
function buildGradeLookup(dim) {
  const lookup = {};
  for (const p of (dim.principles || [])) {
    const key = p.name || p.principle || '';
    if (key) lookup[key] = { grade: p.grade, score: p.score };
  }
  return lookup;
}

/** Count severity levels from a violations array, returning { critical, major, minor } */
function countSeverities(violations) {
  let critical = 0, major = 0, minor = 0;
  for (const v of violations) {
    if (v.severity === 'critical') critical++;
    else if (v.severity === 'major') major++;
    else minor++;
  }
  return { critical, major, minor };
}

/** Compute a principle's score from raw data, grade, or violation ratio */
function computePrincipleScore(rawScore, grade, violationCount, complianceCount) {
  if (rawScore) return parseFloat(rawScore);
  if (grade) return gradeToScore(grade);
  const total = violationCount + complianceCount;
  return total > 0 ? (complianceCount / total) * 10 : 5;
}

const CONSTELLATION_LABELS = {
  builtin: 'ISO Standards', quodeq: 'Quodeq Standards', community: 'Community Standards', custom: 'Custom Standards', _default: '',
};

function buildScene(dimensions, W, H, standardTypes) {
  // Seeded RNG from dimension names for deterministic layout
  const dimFingerprint = dimensions.map(d => d.dimension || '').sort().join('|');
  const rng = seededRng(seedHash('galaxy:' + dimFingerprint));

  // Group dimensions by standard type
  const dimGroups = {};
  dimensions.forEach(dim => {
    const id = (dim.dimension || '').toLowerCase();
    const type = standardTypes[id] || '_default';
    if (!dimGroups[type]) dimGroups[type] = [];
    dimGroups[type].push(dim);
  });

  const groupKeys = Object.keys(dimGroups).filter(k => k !== '_default');
  if (dimGroups._default) groupKeys.push('_default');
  const useConstellations = groupKeys.length > 1 || (groupKeys.length === 1 && groupKeys[0] !== '_default');

  const stars = [];
  const constellations = [];
  let globalIdx = 0;

  const spread = Math.min(W, H) * 0.5;
  const baseClusterSpread = Math.min(W, H) * 0.3;

  if (useConstellations) {
    // Seeded cluster positions — unique per group composition
    const n = groupKeys.length;
    let clusterPositions;
    if (n === 1) {
      clusterPositions = [[0, 0]];
    } else {
      const clusterRng = seededRng(seedHash('clusters:' + groupKeys.join(':')));
      clusterPositions = groupKeys.map(() => {
        const angle = clusterRng() * TAU;
        const dist = 0.3 + clusterRng() * 0.5;
        return [Math.cos(angle) * dist, Math.sin(angle) * dist];
      });
      let cx = 0, cy = 0;
      clusterPositions.forEach(p => { cx += p[0]; cy += p[1]; });
      cx /= n; cy /= n;
      clusterPositions.forEach(p => { p[0] -= cx; p[1] -= cy; });
    }

    groupKeys.forEach((type, gi) => {
      const [px, py] = clusterPositions[gi];
      const clusterCx = px * spread * 1.8;
      const clusterCy = py * spread * 1.8;
      const groupDims = dimGroups[type];
      const clusterSpread = baseClusterSpread + groupDims.length * 12;

      const startIdx = globalIdx;
      const lines = [];

      // Seeded organic layout — scattered but balanced, no center star
      const clRng = seededRng(seedHash('cl:' + type));
      const phaseOffset = clRng() * TAU;
      // Place all stars scattered around the cluster, with seeded variation
      groupDims.forEach((dim, i) => {
        const totalV = dim.totals?.violationCount || dim.violations?.length || 0;
        const totalC = dim.totals?.complianceCount || dim.compliance?.length || 0;
        const score = dim.overallScore ? parseFloat(dim.overallScore) : 5;
        const radius = 3 + Math.sqrt(totalV + totalC) * 0.4;
        const n = groupDims.length;
        // Fully seeded random angle — organic scatter
        const a = phaseOffset + clRng() * TAU;
        // Distance: varied per star, seeded — closer and further stars mixed
        const distVar = 0.3 + clRng() * 0.45; // 0.3 to 0.75
        const dist = n === 1 ? 0 : Math.max(clusterSpread * distVar, 40);
        stars.push({
          name: dim.dimension || 'Unknown',
          score, radius,
          violations: totalV, compliance: totalC,
          col: scoreRGB(score),
          ba: 0, j: 0,
          _clusterCx: clusterCx,
          _clusterCy: clusterCy,
          _ox: Math.cos(a) * dist,
          _oy: Math.sin(a) * dist,
          pp: rng() * TAU,
          x: 0, y: 0,
          principleCount: 0,
          _raw: dim,
        });
        globalIdx++;
      });
      // MST constellation lines — connects all stars, organic shape
      const clusterStars = stars.slice(startIdx);
      if (clusterStars.length >= 2) {
        const connected = new Set([0]);
        while (connected.size < clusterStars.length) {
          let bestA = -1, bestB = -1, bestD = Infinity;
          for (const ai of connected) {
            for (let bi = 0; bi < clusterStars.length; bi++) {
              if (connected.has(bi)) continue;
              const dx = clusterStars[ai]._ox - clusterStars[bi]._ox;
              const dy = clusterStars[ai]._oy - clusterStars[bi]._oy;
              const d = dx * dx + dy * dy;
              if (d < bestD) { bestD = d; bestA = ai; bestB = bi; }
            }
          }
          if (bestB >= 0) { lines.push({ a: startIdx + bestA, b: startIdx + bestB }); connected.add(bestB); }
          else break;
        }
      }

      // Repulsion pass — enforce minimum distance between stars in cluster
      const clStars = stars.slice(startIdx);
      const minGap = 60;
      const clIters = clStars.length > 30 ? 3 : 6;
      for (let iter = 0; iter < clIters; iter++) {
        for (let a2 = 0; a2 < clStars.length; a2++) {
          for (let b2 = a2 + 1; b2 < clStars.length; b2++) {
            const sa = clStars[a2], sb = clStars[b2];
            const dx = sb._ox - sa._ox, dy = sb._oy - sa._oy;
            const d = Math.sqrt(dx * dx + dy * dy) || 0.1;
            const minD = sa.radius + sb.radius + minGap;
            if (d < minD) {
              const push = (minD - d) / 2;
              const nx = dx / d, ny = dy / d;
              sa._ox -= nx * push; sa._oy -= ny * push;
              sb._ox += nx * push; sb._oy += ny * push;
            }
          }
        }
      }
      // Re-center after repulsion
      if (clStars.length > 0) {
        let rcx = 0, rcy = 0;
        clStars.forEach(s => { rcx += s._ox; rcy += s._oy; });
        rcx /= clStars.length; rcy /= clStars.length;
        clStars.forEach(s => { s._ox -= rcx; s._oy -= rcy; });
      }

      constellations.push({ type, label: CONSTELLATION_LABELS[type] || type, cx: clusterCx, cy: clusterCy, spread: clusterSpread, lines });
    });
  } else {
    // Single group — seeded circular layout
    dimensions.forEach((dim, i) => {
      const totalV = dim.totals?.violationCount || dim.violations?.length || 0;
      const totalC = dim.totals?.complianceCount || dim.compliance?.length || 0;
      const score = dim.overallScore ? parseFloat(dim.overallScore) : 5;
      const radius = 3 + Math.sqrt(totalV + totalC) * 0.4;
      stars.push({
        name: dim.dimension || 'Unknown',
        score, radius,
        violations: totalV, compliance: totalC,
        col: scoreRGB(score),
        ba: (i / dimensions.length) * TAU - Math.PI / 2,
        j: (rng() - 0.5) * 40,
        _clusterCx: 0, _clusterCy: 0, _ox: 0, _oy: 0,
        pp: rng() * TAU,
        x: 0, y: 0,
        principleCount: 0,
        _raw: dim,
      });
    });
  }

  // Level 1: Principles per dimension
  const principles = {};
  dimensions.forEach((dim, di) => {
    const groups = groupByPrinciple(dim);
    const gradeLookup = buildGradeLookup(dim);
    const prinList = Object.entries(groups).map(([name, g]) => ({
      name,
      grade: gradeLookup[name]?.grade || null,
      score: gradeLookup[name]?.score || null,
      violations: g.violations,
      compliance: g.compliance,
    }));
    const pRng = seededRng(seedHash('prin:' + (dim.dimension || di)));
    principles[di] = prinList.map((p, pi) => {
      const pv = p.violations.length;
      const pc = p.compliance.length;
      const pScore = computePrincipleScore(p.score, p.grade, pv, pc);
      const radius = 6 + Math.sqrt(pv + pc) * 1.5;
      const sev = countSeverities(p.violations);
      return {
        name: p.name,
        grade: p.grade,
        score: pScore,
        rawScore: p.score,
        violations: pv, compliance: pc,
        radius, col: scoreRGB(pScore),
        ba: (pi / (prinList.length || 1)) * TAU - Math.PI / 2,
        od: 25 + (pi / (prinList.length || 1)) * 35 + pRng() * 5,
        pp: pRng() * TAU,
        ...sev,
        x: 0, y: 0,
        particles: mkParticles(sev.critical, sev.major, sev.minor, radius),
        _rawViolations: p.violations,
        _rawCompliance: p.compliance,
        dimParticle: {
          col: scoreRGB(pScore),
          or: 12 + Math.sqrt(pv + pc) * 1.5,
          os: (0.02 + pRng() * 0.05) * (pRng() > 0.5 ? 1 : -1),
          op: pRng() * TAU,
          sz: 0.8 + Math.sqrt(pv + pc) * 0.15,
          ec: 0.9 + pRng() * 0.1,
          tp: pRng() * TAU,
        },
      };
    });
  });

  stars.forEach((s, i) => { s.principleCount = (principles[i] || []).length; });

  // Connections between dimensions that share files — build a file→dim index for efficiency
  const dimFiles = dimensions.map(d => new Set((d.violations || []).map(v => v.file).filter(Boolean)));
  const connections = [];
  const fileToDims = new Map();
  dimFiles.forEach((files, idx) => {
    files.forEach(f => {
      if (!fileToDims.has(f)) fileToDims.set(f, []);
      fileToDims.get(f).push(idx);
    });
  });
  const sharedCounts = new Map();
  fileToDims.forEach((dimIdxs) => {
    for (let a = 0; a < dimIdxs.length; a++) {
      for (let b = a + 1; b < dimIdxs.length; b++) {
        const key = dimIdxs[a] < dimIdxs[b] ? `${dimIdxs[a]}-${dimIdxs[b]}` : `${dimIdxs[b]}-${dimIdxs[a]}`;
        sharedCounts.set(key, (sharedCounts.get(key) || 0) + 1);
      }
    }
  });
  sharedCounts.forEach((shared, key) => {
    const [i, j] = key.split('-').map(Number);
    const maxFiles = Math.max(dimFiles[i].size, dimFiles[j].size, 1);
    connections.push({ a: i, b: j, s: Math.min(1, shared / maxFiles) });
  });

  const bgRng = seededRng(seedHash('bg:' + dimFingerprint));
  const bg = Array.from({ length: 120 }, () => ({
    x: bgRng(), y: bgRng(),
    sz: bgRng() * 1.2,
    tw: bgRng() * TAU,
    sp: 0.3 + bgRng() * 0.7,
  }));

  // Compute max extent for fitZoom — include constellation circle + label space
  let _maxExtentX = 0, _maxExtentY = 0;
  stars.forEach(s => {
    const ex = Math.abs(s._clusterCx + s._ox) + s.radius * 2;
    const ey = Math.abs(s._clusterCy + s._oy) + s.radius * 2;
    if (ex > _maxExtentX) _maxExtentX = ex;
    if (ey > _maxExtentY) _maxExtentY = ey;
  });
  constellations.forEach(con => {
    const ex = Math.abs(con.cx) + con.spread + 40;
    const ey = Math.abs(con.cy) + con.spread + 50; // extra for label above
    if (ex > _maxExtentX) _maxExtentX = ex;
    if (ey > _maxExtentY) _maxExtentY = ey;
  });
  const _maxExtent = Math.max(_maxExtentX, _maxExtentY);

  return { stars, principles, connections, constellations, bg, _maxExtent };
}

// Module-level saved state — persists across unmount/remount (back from detail)
let _savedGalaxyNav = null;
let _savedGalaxyCam = null;

export default function GalaxyView({ dimensions, onNavigate, showLabels = true, setShowLabels, resetKey = 0, projectName = '', standardTypes = {} }) {
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

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
    if (!scene || dimensions.length === 0) return;
    dimensions.forEach((dim, di) => {
      const star = scene.stars[di];
      if (!star) return;
      const totalV = dim.totals?.violationCount || dim.violations?.length || 0;
      const totalC = dim.totals?.complianceCount || dim.compliance?.length || 0;
      const score = dim.overallScore ? parseFloat(dim.overallScore) : 5;
      star.violations = totalV;
      star.compliance = totalC;
      star.score = score;
      star.col = scoreRGB(score);
      star._raw = dim;

      const groups = groupByPrinciple(dim);
      const gradeLookup = buildGradeLookup(dim);

      (scene.principles[di] || []).forEach(prin => {
        const g = groups[prin.name];
        if (!g) { prin.violations = 0; prin.compliance = 0; prin._rawViolations = []; prin._rawCompliance = []; prin.particles = []; return; }
        const pv = g.violations.length;
        const pc = g.compliance.length;
        const gl = gradeLookup[prin.name];
        const pScore = computePrincipleScore(gl?.score, gl?.grade, pv, pc);
        const sev = countSeverities(g.violations);
        prin.violations = pv;
        prin.compliance = pc;
        prin.score = pScore;
        prin.rawScore = gl?.score || null;
        prin.grade = gl?.grade || null;
        prin.col = scoreRGB(pScore);
        prin._rawViolations = g.violations;
        prin._rawCompliance = g.compliance;
        if (sev.critical !== prin.critical || sev.major !== prin.major || sev.minor !== prin.minor) {
          prin.particles = mkParticles(sev.critical, sev.major, sev.minor, prin.radius);
        }
        prin.critical = sev.critical; prin.major = sev.major; prin.minor = sev.minor;
      });
    });
    // Update star principle counts
    scene.stars.forEach((s, i) => { s.principleCount = (scene.principles[i] || []).length; });
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
  const hasSavedDeep = _savedGalaxyNav && _savedGalaxyNav.depth > 0;
  const camRef = useRef(_savedGalaxyCam ? { ..._savedGalaxyCam } : null);
  const navRef = useRef(hasSavedDeep ? { ..._savedGalaxyNav } : { depth: 0, dim: null, prin: null });
  const animRef = useRef(null);
  const frameCount = useRef(0); // snap camera for first few frames to let positions settle
  const [navVersion, setNavVersion] = useState(0);
  const timeRef = useRef(0);
  const mouseRef = useRef({ x: -1, y: -1 });
  const hoveredRef = useRef(null);
  const tooltipRef = useRef(null);
  const frameRef = useRef(null);

  const TRANS = 0.8;

  // Save nav state to module-level variable and trigger re-render
  const saveNav = useCallback(() => {
    _savedGalaxyNav = { ...navRef.current };
    _savedGalaxyCam = { ...camRef.current };
    setNavVersion(v => v + 1);
  }, []);

  // Start animated transition from current camera to new target
  const prevNavRef = useRef(null); // previous nav state — rendered during zoom-out until new level appears
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
      _savedGalaxyNav = null;
      _savedGalaxyCam = null;
      startTransition(true);
      saveNav();
    }
  }, [resetKey, saveNav, startTransition]);

  // World-to-screen transform
  const w2s = useCallback((wx, wy) => {
    const cam = camRef.current;
    return { x: (wx - cam.x) * cam.z + size.w / 2, y: (wy - cam.y) * cam.z + size.h / 2 };
  }, [size.w, size.h]);

  // Compute fitZoom from scene extent
  const getFitZoom = useCallback(() => {
    const ext = scene?._maxExtent;
    if (!ext || ext <= 0) return 1;
    const halfView = Math.min(size.w, size.h) / 2 - 20;
    return Math.min(halfView / ext, 4);
  }, [scene, size.w, size.h]);

  // Get camera target for current depth
  const getTarget = useCallback(() => {
    const nav = navRef.current;
    const fz = getFitZoom();
    if (nav.depth === 0) {
      if (nav.clusterCx != null) {
        // Fit zoom to cluster spread + padding
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

    // Reset camera on scene change so it starts at correct fitZoom
    if (camRef.current?._sceneId !== scene) {
      camRef.current = null;
      frameCount.current = 0;
    }

    function frame() {
      if (!running) return;
      const t = timeRef.current += 0.016;
      const nav = navRef.current;
      const W = size.w, H = size.h;
      if (!camRef.current) camRef.current = { x: W / 2, y: H / 2, z: getFitZoom(), _sceneId: scene };
      const cam = camRef.current;
      const SP = Math.min(W, H) * 0.22;

      // Update star world positions
      scene.stars.forEach((s, i) => {
        if (s._clusterCx !== undefined) {
          // Constellation layout: offset from cluster center with gentle drift
          const drift = Math.sin(t * 0.015 + i * 1.1) * 2;
          s.x = W / 2 + s._clusterCx + s._ox + drift;
          s.y = H / 2 + s._clusterCy + s._oy + Math.cos(t * 0.012 + i * 0.8) * 2;
        } else {
          // Fallback: circular orbit
          const a = s.ba + Math.sin(t * 0.02 + i * 0.7) * 0.03;
          s.x = W / 2 + Math.cos(a) * (SP + s.j);
          s.y = H / 2 + Math.sin(a) * (SP + s.j);
        }
      });
      // Render nav: during zoom-out, keep using previous nav so deeper content stays positioned
      const prev = prevNavRef.current;
      const rDim = nav.dim ?? prev?.dim ?? null;
      const rPrin = nav.prin ?? prev?.prin ?? null;

      // Update principle positions
      if (rDim !== null) {
        const dim = scene.stars[rDim];
        (scene.principles[rDim] || []).forEach((p, pi) => {
          const speed = 0.008 + pi * 0.003; // each principle orbits at its own speed
          const wobble = Math.sin(t * 0.04 + pi * 2.1) * 0.02;
          p.x = dim.x + Math.cos(p.ba + t * speed + wobble) * p.od;
          p.y = dim.y + Math.sin(p.ba + t * speed + wobble) * p.od;
        });
      }

      // --- Camera ---
      const tg = getTarget();
      const anim = animRef.current;
      frameCount.current++;
      if (!anim && frameCount.current <= 3) {
        // Snap for first frames to let positions settle
        cam.x = tg.x; cam.y = tg.y; cam.z = tg.z;
      } else if (!anim) {
        // Idle: soft drift toward target
        cam.x += (tg.x - cam.x) * 0.06;
        cam.y += (tg.y - cam.y) * 0.06;
        cam.z += (tg.z - cam.z) * 0.06;
      } else {
        // Animated transition
        anim.t = Math.min(1, anim.t + 0.016 / TRANS);
        const ease = anim.t < 0.5 ? 4 * anim.t * anim.t * anim.t : 1 - Math.pow(-2 * anim.t + 2, 3) / 2;
        const lag = Math.pow(anim.t, 0.7); const lagE = lag * lag * (3 - 2 * lag);
        // Zoom-in: position lags behind zoom. Zoom-out: mirror — zoom lags behind position.
        const posE = anim.out ? ease : lagE;
        const zoomE = anim.out ? lagE : ease;
        cam.x = anim.sx + (tg.x - anim.sx) * posE;
        cam.y = anim.sy + (tg.y - anim.sy) * posE;
        cam.z = anim.sz + (tg.z - anim.sz) * zoomE;
        if (anim.t >= 1) { animRef.current = null; prevNavRef.current = null; }
      }

      // --- Draw ---
      // Background (uses theme colors)
      const tc = getThemeColors();
      const grad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.6);
      grad.addColorStop(0, tc.bgAlt); grad.addColorStop(1, tc.bg);
      ctx.fillStyle = grad; ctx.fillRect(0, 0, W, H);
      const { r: mr, g: mg, b: mb } = tc.textMuted;
      scene.bg.forEach(s => {
        const a = 0.15 + 0.15 * Math.sin(t * s.sp + s.tw);
        ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.sz, 0, TAU);
        ctx.fillStyle = `rgba(${mr},${mg},${mb},${a})`; ctx.fill();
      });

      // Constellation lines and labels (only at galaxy level)
      if (cam.z < 3) {
        const conAlpha = Math.max(0, 1 - (cam.z - 1) / 2);
        (scene.constellations || []).forEach(con => {
          const isFocused = nav.clusterCx == null || (con.cx === nav.clusterCx && con.cy === nav.clusterCy);
          const conClusterDim = isFocused ? 1 : Math.max(0.08, 1 - (cam.z - 1) / 2);
          // Dashed circle around cluster
          const csc = w2s(W / 2 + con.cx, H / 2 + con.cy);
          const circleR = (con.spread + 10) * cam.z;
          ctx.beginPath(); ctx.arc(csc.x, csc.y, circleR, 0, TAU);
          ctx.strokeStyle = `rgba(${mr},${mg},${mb},${0.15 * conAlpha * conClusterDim})`;
          ctx.lineWidth = 1;
          ctx.setLineDash([8, 14]); ctx.stroke(); ctx.setLineDash([]);

          // Constellation lines between stars
          con.lines.forEach(l => {
            const sa = w2s(scene.stars[l.a].x, scene.stars[l.a].y);
            const sb = w2s(scene.stars[l.b].x, scene.stars[l.b].y);
            ctx.beginPath(); ctx.moveTo(sa.x, sa.y); ctx.lineTo(sb.x, sb.y);
            ctx.strokeStyle = `rgba(${mr},${mg},${mb},${0.4 * conAlpha * conClusterDim})`;
            ctx.lineWidth = 0.8;
            ctx.setLineDash([3, 5]); ctx.stroke(); ctx.setLineDash([]);
          });
          // Constellation label — above the dashed circle
          if (showLabels && con.label) {
            const lx = csc.x;
            const ly = csc.y - circleR - 10;
            ctx.font = '600 14px -apple-system,BlinkMacSystemFont,sans-serif';
            ctx.textAlign = 'center';
            ctx.fillStyle = `rgba(${mr},${mg},${mb},${0.55 * conAlpha * conClusterDim})`;
            ctx.fillText(con.label, lx, ly);
            con._lx = lx; con._ly = ly;
          }
        });
      }

      // Dimension stars + principle particles orbiting them
      const mx = mouseRef.current.x, my = mouseRef.current.y;
      let newHovered = null;
      scene.stars.forEach((s, i) => {
        const sc = w2s(s.x, s.y);
        const pulse = 1 + 0.01 * Math.sin(t * 0.4 + s.pp);
        const isSelected = rDim === i;
        const sr = s.radius * pulse * cam.z * 0.5;
        // Dim stars not in the focused cluster
        const inFocusedCluster = nav.clusterCx == null || (s._clusterCx === nav.clusterCx && s._clusterCy === nav.clusterCy);
        const clusterDim = inFocusedCluster ? 1 : Math.max(0.08, 1 - (cam.z - 1) / 2);
        // All dim-level decorations fade out once we zoom past galaxy level
        const dimFade = isSelected ? 1 : Math.max(0, 1 - (cam.z - 1.5) / 3) * clusterDim;

        // Principle particles orbiting this dimension — fade out as principle planets fade in
        const particleAlpha = isSelected ? Math.max(0, 1 - (cam.z - 1.5) / 2) : dimFade;
        if (particleAlpha > 0.01) {
          (scene.principles[i] || []).forEach(p => {
            const dp = p.dimParticle;
            const a = t * dp.os + dp.op;
            const px = sc.x + Math.cos(a) * dp.or * dp.ec * cam.z;
            const py = sc.y + Math.sin(a) * dp.or * cam.z;
            const tw = 0.5 + 0.08 * Math.sin(t * 0.6 + dp.tp);
            const sz = dp.sz * cam.z;
            if (sz > 0.3) {
              const { r, g, b } = dp.col;
              ctx.beginPath(); ctx.arc(px, py, sz * 2.5, 0, TAU);
              ctx.fillStyle = `rgba(${r},${g},${b},${tw * 0.08 * particleAlpha})`; ctx.fill();
              ctx.beginPath(); ctx.arc(px, py, sz, 0, TAU);
              ctx.fillStyle = `rgba(${r},${g},${b},${(tw + 0.15) * particleAlpha})`; ctx.fill();
            }
          });
        }

        drawGlow(ctx, sc.x, sc.y, sr, s.col, isSelected ? clusterDim : dimFade);
        // Hide dimension label when zoomed past galaxy level
        const labelAlpha = isSelected ? Math.max(0, 1 - (cam.z - 1.5) / 2) : dimFade;
        if (showLabels && labelAlpha > 0.01) {
          const fs = Math.min(cam.z, 1.5);
          ctx.font = `600 ${Math.max(11, 14 * fs)}px -apple-system,BlinkMacSystemFont,sans-serif`;
          ctx.textAlign = 'center'; ctx.fillStyle = rgba(tc.text, 0.6 * labelAlpha);
          ctx.fillText(s.name, sc.x, sc.y - sr - 24 * fs);
          ctx.font = `${Math.max(9, 12 * fs)}px -apple-system,BlinkMacSystemFont,sans-serif`;
          ctx.fillStyle = rgba(tc.textMuted, 0.8 * labelAlpha);
          ctx.fillText(s.score.toFixed(1), sc.x, sc.y + sr + 24 * fs);
        }
        if (!anim && nav.depth === 0 && mx >= 0) {
          const dx = mx - sc.x, dy = my - sc.y;
          const hitR = Math.max(sr * 2, 20);
          if (dx * dx + dy * dy < hitR * hitR) newHovered = { type: 'dim', idx: i, data: s };
        }
      });

      // Principles as planets (visible when zoomed into a dimension)
      if (cam.z > 1.5 && rDim !== null) {
        const dim = scene.stars[rDim];
        const dsc = w2s(dim.x, dim.y);
        const pAlpha = Math.min(1, (cam.z - 1.5) / 3);
        const pScale = cam.z * 0.12;
        (scene.principles[rDim] || []).forEach((p, pi) => {
          const isSelectedPrin = nav.prin === pi;
          const sc = w2s(p.x, p.y);
          const sr = p.radius * pScale;
          // orbit ring
          ctx.beginPath(); ctx.arc(dsc.x, dsc.y, Math.hypot(sc.x - dsc.x, sc.y - dsc.y), 0, TAU);
          ctx.strokeStyle = `rgba(50,55,80,${0.1 * pAlpha})`; ctx.lineWidth = 0.5; ctx.stroke();
          // connection line
          ctx.beginPath(); ctx.moveTo(dsc.x, dsc.y); ctx.lineTo(sc.x, sc.y);
          ctx.strokeStyle = rgba(dim.col, 0.04 * pAlpha); ctx.lineWidth = 0.8; ctx.stroke();
          // Violation/compliance particles — fade out on selected (large orbs take over), shrink on others
          const particleFade = isSelectedPrin ? Math.max(0, 1 - (cam.z - 12) / 20) : 1;
          // Non-selected: smaller particles but keep orbit wide so they don't collide with planet
          const cappedScale = Math.min(0.8, 5 * 0.12 / Math.max(pScale, 0.01));
          const particleDrawScale = isSelectedPrin ? pScale * 0.8 : pScale * cappedScale;
          const particleOrbitScale = isSelectedPrin ? pScale * 0.8 : pScale * Math.max(cappedScale, 0.5);
          if (particleFade > 0.01) drawParticles(ctx, sc.x, sc.y, p.particles, particleOrbitScale, pAlpha * particleFade, t, particleDrawScale);
          drawGlow(ctx, sc.x, sc.y, sr, p.col, pAlpha);
          // Only fade labels/scores — hide on non-selected when zoomed into a principle
          const prinLabelAlpha = isSelectedPrin ? Math.max(0, 1 - (cam.z - 12) / 20) : (nav.prin !== null ? Math.max(0, 1 - (cam.z - 12) / 15) : 1);
          if (showLabels && prinLabelAlpha > 0.01) {
            const la = pAlpha * prinLabelAlpha;
            ctx.font = `600 14px -apple-system,BlinkMacSystemFont,sans-serif`;
            ctx.textAlign = 'center'; ctx.fillStyle = rgba(tc.text, 0.6 * la);
            ctx.fillText(p.name, sc.x, sc.y - sr - 10);
            ctx.font = `12px -apple-system,BlinkMacSystemFont,sans-serif`;
            ctx.fillStyle = rgba(tc.textMuted, 0.7 * la);
            ctx.fillText(p.score.toFixed(1), sc.x, sc.y + sr + 16);
          }
          if (!anim && nav.depth === 1 && pAlpha > 0.4 && mx >= 0) {
            const dx = mx - sc.x, dy = my - sc.y;
            if (dx * dx + dy * dy < (sr + 10) * (sr + 10)) newHovered = { type: 'prin', idx: pi, data: p };
          }
        });
      }

      // Zoomed into principle — violation/compliance particles as large orbs
      if (cam.z > 12 && rDim !== null && rPrin !== null) {
        const prin = scene.principles[rDim][rPrin];
        const psc = w2s(prin.x, prin.y);
        const vAlpha = Math.min(1, (cam.z - 12) / 20);
        const vScale = cam.z * 0.06;
        prin.particles.forEach((p, pi) => {
          const a = t * p.os + p.op;
          const px = psc.x + Math.cos(a) * p.or * p.ec * vScale;
          const py = psc.y + Math.sin(a) * p.or * vScale;
          const tw = 0.5 + 0.06 * Math.sin(t * 0.4 + p.tp);
          const sr = p.sz * vScale * 0.5;
          drawGlow(ctx, px, py, sr, p.col, vAlpha * tw);
          if (showLabels && sr > 3) {
            const sevName = p.sev.charAt(0).toUpperCase() + p.sev.slice(1);
            ctx.font = `500 ${Math.max(7, Math.min(11, sr * 0.8))}px -apple-system,BlinkMacSystemFont,sans-serif`;
            ctx.textAlign = 'center'; ctx.fillStyle = rgba(p.col, 0.85 * vAlpha);
            ctx.fillText(sevName, px, py - sr - 4);
          }
        });
      }

      hoveredRef.current = newHovered;
      frameRef.current = requestAnimationFrame(frame);
    }

    frameRef.current = requestAnimationFrame(frame);
    return () => { running = false; cancelAnimationFrame(frameRef.current); };
  }, [scene, size, showLabels, w2s, getTarget]);

  // --- Mouse + click handlers ---
  const handleMouseMove = useCallback((e) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    // Update cursor
    canvasRef.current.style.cursor = hoveredRef.current && navRef.current.depth < 2 ? 'pointer' : 'default';
    // Update tooltip
    updateTooltip(e.clientX, e.clientY);
  }, []);

  const handleMouseLeave = useCallback(() => {
    mouseRef.current = { x: -1, y: -1 };
    hoveredRef.current = null;
    if (tooltipRef.current) tooltipRef.current.style.display = 'none';
  }, []);

  // Unified navigation — handles zoom in, zoom out, and reset
  const navigateTo = useCallback((depth, dim, prin) => {
    if (animRef.current) return; // already transitioning
    const wasDepth = navRef.current.depth;
    const zoomingOut = depth < wasDepth;
    if (zoomingOut) prevNavRef.current = { ...navRef.current };
    navRef.current = { depth, dim: dim ?? null, prin: prin ?? null };
    startTransition(zoomingOut);
    saveNav();
  }, [saveNav, startTransition]);

  const handleClick = useCallback((e) => {
    const h = hoveredRef.current;
    const nav = navRef.current;
    if (h) {
      if (nav.depth === 0 && h.type === 'dim') navigateTo(1, h.idx);
      else if (nav.depth === 1 && h.type === 'prin') navigateTo(2, nav.dim, h.idx);
      return;
    }
    // At galaxy root: check if click is near a cluster → zoom to it
    if (nav.depth === 0 && !animRef.current && scene?.constellations) {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (rect) {
        const cmx = e.clientX - rect.left, cmy = e.clientY - rect.top;
        for (const con of scene.constellations) {
          const csc = w2s(size.w / 2 + con.cx, size.h / 2 + con.cy);
          const dx = cmx - csc.x, dy = cmy - csc.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const hitRadius = (con.spread + 40) * camRef.current.z;
          if (dist < hitRadius) {
            if (nav.clusterCx === con.cx && nav.clusterCy === con.cy) {
              // Already in this cluster — zoom back to galaxy
              nav.clusterCx = null; nav.clusterCy = null;
              startTransition(true);
            } else {
              // Zoom to this cluster
              nav.clusterCx = con.cx; nav.clusterCy = con.cy;
              startTransition(false);
            }
            saveNav();
            return;
          }
        }
      }
    }
    // Click empty space (outside any cluster)
    if (nav.depth > 0) {
      if (nav.depth === 2) navigateTo(1, nav.dim);
      else navigateTo(0);
    } else if (nav.clusterCx != null) {
      // Zoomed into cluster but clicked far from it — zoom back
      nav.clusterCx = null; nav.clusterCy = null;
      startTransition(true);
      saveNav();
    }
  }, [navigateTo, startTransition, saveNav, scene]);

  const goToDepth = useCallback((d) => {
    const nav = navRef.current;
    if (d >= nav.depth) return;
    if (d <= 0) navigateTo(0);
    else if (d === 1) navigateTo(1, nav.dim);
  }, [navigateTo]);

  // Tooltip updater
  const updateTooltip = useCallback((cx, cy) => {
    const el = tooltipRef.current;
    if (!el) return;
    const h = hoveredRef.current;
    if (!h || animRef.current) { el.style.display = 'none'; return; }
    const d = h.data;
    const row = (label, value, color) => `<div style="display:flex;justify-content:space-between;gap:12px;color:${color || 'var(--color-text-muted)'}"><span>${label}</span><span style="color:${color || 'var(--color-text)'};font-weight:500">${value}</span></div>`;
    const rows = [row('Score', d.score.toFixed(1))];
    if (h.type === 'dim') rows.push(row('Principles', d.principleCount));
    rows.push(row('Violations', d.violations));
    if (d.violations > 0) {
      // For dimensions: compute severity from raw violations; for principles: use stored counts
      let sc = d.critical, sm = d.major, sn = d.minor;
      if (sc == null && d._raw?.violations) {
        sc = sm = sn = 0;
        (d._raw.violations || []).forEach(v => {
          const s = v.severity || 'minor';
          if (s === 'critical') sc++;
          else if (s === 'major') sm++;
          else sn++;
        });
      }
      if (sc > 0) rows.push(row('Critical', sc, 'var(--color-sev-critical-text)'));
      if (sm > 0) rows.push(row('Major', sm, 'var(--color-sev-major-text)'));
      if (sn > 0) rows.push(row('Minor', sn, 'var(--color-sev-minor-text)'));
    }
    rows.push(row('Compliance', d.compliance));
    el.innerHTML = `<div style="font-weight:600;color:${rgb(d.col)};margin-bottom:4px">${d.name}</div>
      ${rows.join('')}
      <div style="margin-top:6px;color:var(--color-text-muted);font-size:11px;opacity:0.6">Click to explore</div>`;
    el.style.display = 'block';
    el.style.left = Math.min(cx + 16, window.innerWidth - 200) + 'px';
    el.style.top = Math.min(cy + 16, window.innerHeight - 160) + 'px';
  }, []);

  // Breadcrumb builder
  const breadcrumb = useMemo(() => {
    const nav = navRef.current;
    const parts = [{ label: projectName ? `${projectName} System` : 'System', depth: 0, action: () => { nav.clusterCx = null; nav.clusterCy = null; } }];
    // Add cluster breadcrumb if focused or zoomed into a dimension that belongs to a cluster
    const star = nav.dim !== null ? scene?.stars[nav.dim] : null;
    const clusterCx = nav.clusterCx ?? star?._clusterCx;
    const clusterCy = nav.clusterCy ?? star?._clusterCy;
    const clusterCon = clusterCx != null ? (scene?.constellations || []).find(c => c.cx === clusterCx && c.cy === clusterCy) : null;
    if (clusterCon) parts.push({ label: clusterCon.label, depth: 0, action: () => { nav.clusterCx = clusterCon.cx; nav.clusterCy = clusterCon.cy; } });
    if (nav.dim !== null && scene) parts.push({ label: scene.stars[nav.dim].name, depth: 1 });
    if (nav.prin !== null && scene) parts.push({ label: scene.principles[nav.dim][nav.prin].name, depth: 2 });
    return parts;
  }, [scene, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Context info for current depth
  const levelInfo = useMemo(() => {
    const nav = navRef.current;
    if (nav.depth === 0) {
      // Filter stars for the focused cluster, or use all
      const clusterStars = nav.clusterCx != null
        ? scene.stars.filter(s => s._clusterCx === nav.clusterCx && s._clusterCy === nav.clusterCy)
        : scene.stars;
      const clusterCon = nav.clusterCx != null
        ? (scene.constellations || []).find(c => c.cx === nav.clusterCx && c.cy === nav.clusterCy)
        : null;
      const totalV = clusterStars.reduce((s, d) => s + d.violations, 0);
      const totalC = clusterStars.reduce((s, d) => s + d.compliance, 0);
      const avgScore = clusterStars.length > 0 ? clusterStars.reduce((s, d) => s + d.score, 0) / clusterStars.length : 0;
      const sevCounts = { critical: 0, major: 0, minor: 0 };
      clusterStars.forEach(s => {
        (s._raw?.violations || []).forEach(v => {
          const sev = v.severity || 'minor';
          if (sevCounts[sev] != null) sevCounts[sev]++;
        });
      });
      const lines = [
        { label: 'Score', value: avgScore.toFixed(1) },
        { label: 'Dimensions', value: clusterStars.length },
        { label: 'Violations', value: totalV },
      ];
      if (totalV > 0) {
        if (sevCounts.critical > 0) lines.push({ label: 'Critical', value: sevCounts.critical, color: 'var(--color-sev-critical-text)' });
        if (sevCounts.major > 0) lines.push({ label: 'Major', value: sevCounts.major, color: 'var(--color-sev-major-text)' });
        if (sevCounts.minor > 0) lines.push({ label: 'Minor', value: sevCounts.minor, color: 'var(--color-sev-minor-text)' });
      }
      lines.push({ label: 'Compliance', value: totalC });
      return {
        title: clusterCon?.label || (projectName ? `${projectName} System` : 'Project System'),
        lines,
        hint: 'Click a dimension to explore',
        detailAction: null,
      };
    }
    if (nav.depth === 1 && nav.dim !== null) {
      const dim = scene.stars[nav.dim];
      const prins = scene.principles[nav.dim] || [];
      const rawDim = dim._raw;
      const dimSev = { critical: 0, major: 0, minor: 0 };
      (rawDim?.violations || []).forEach(v => {
        const sev = v.severity || 'minor';
        if (dimSev[sev] != null) dimSev[sev]++;
      });
      const dimLines = [
        { label: 'Score', value: dim.score.toFixed(1) },
        { label: 'Principles', value: prins.length },
        { label: 'Violations', value: dim.violations },
      ];
      if (dim.violations > 0) {
        if (dimSev.critical > 0) dimLines.push({ label: 'Critical', value: dimSev.critical, color: 'var(--color-sev-critical-text)' });
        if (dimSev.major > 0) dimLines.push({ label: 'Major', value: dimSev.major, color: 'var(--color-sev-major-text)' });
        if (dimSev.minor > 0) dimLines.push({ label: 'Minor', value: dimSev.minor, color: 'var(--color-sev-minor-text)' });
      }
      dimLines.push({ label: 'Compliance', value: dim.compliance });
      return {
        title: dim.name,
        lines: dimLines,
        hint: 'Click a principle to explore',
        detailAction: () => {
          const d = scene.stars[navRef.current.dim]?._raw;
          if (!d) return;
          onNavigate?.('explorer', { dimension: d.dimension, runId: d.fromRunId, dateLabel: d.fromDateLabel, fromProject: d.fromProject, sourceTab: 'map' });
        },
      };
    }
    if (nav.depth === 2 && nav.dim !== null && nav.prin !== null) {
      const prin = scene.principles[nav.dim][nav.prin];
      const prinLines = [
        { label: 'Score', value: prin.score.toFixed(1) },
        { label: 'Violations', value: prin.violations },
      ];
      if (prin.violations > 0) {
        if (prin.critical > 0) prinLines.push({ label: 'Critical', value: prin.critical, color: 'var(--color-sev-critical-text)' });
        if (prin.major > 0) prinLines.push({ label: 'Major', value: prin.major, color: 'var(--color-sev-major-text)' });
        if (prin.minor > 0) prinLines.push({ label: 'Minor', value: prin.minor, color: 'var(--color-sev-minor-text)' });
      }
      prinLines.push({ label: 'Compliance', value: prin.compliance });
      return {
        title: prin.name,
        lines: prinLines,
        hint: null,
        // Read live data at click time, not at memo time
        detailAction: () => {
          const p = scene.principles[navRef.current.dim]?.[navRef.current.prin];
          const d = scene.stars[navRef.current.dim];
          if (!p || !d) return;
          onNavigate?.('evalprinciple', {
            evalPrincipal: {
              principle: p.name,
              score: p.rawScore || (p.score != null ? p.score.toFixed(1) : null),
              grade: p.grade,
              dimension: d.name,
              principleData: {
                name: p.name,
                grade: p.grade,
                violations: p._rawViolations,
                compliance: p._rawCompliance,
              },
              dimViolations: p._rawViolations,
              dimCompliance: p._rawCompliance,
            },
            sourceTab: 'map',
          });
        },
      };
    }
    return null;
  }, [scene, navVersion]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fade in once constellations are ready (avoids showing centered layout before standards load)
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
      />
      {/* Breadcrumb */}
      <div style={{ position: 'absolute', top: 8, left: 12, display: 'flex', gap: 4, alignItems: 'center', fontSize: 12, zIndex: 2 }}>
        {breadcrumb.map((bc, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {i > 0 && <span style={{ color: 'var(--color-border)' }}>{'\u203A'}</span>}
            <span
              style={{ color: i === breadcrumb.length - 1 ? 'var(--color-text)' : 'var(--color-text-muted)', cursor: i < breadcrumb.length - 1 ? 'pointer' : 'default', padding: '3px 8px', borderRadius: 4, transition: 'all 0.2s' }}
              onClick={i < breadcrumb.length - 1 ? () => {
                if (bc.action) { bc.action(); startTransition(true); saveNav(); }
                else goToDepth(bc.depth);
              } : undefined}
              onMouseEnter={i < breadcrumb.length - 1 ? (e) => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 15%, transparent)'; e.target.style.color = 'var(--color-text)'; } : undefined}
              onMouseLeave={i < breadcrumb.length - 1 ? (e) => { e.target.style.background = 'transparent'; e.target.style.color = 'var(--color-text-muted)'; } : undefined}
            >{bc.label}</span>
          </span>
        ))}
      </div>
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
      {/* Labels toggle */}
      <label className="map-label-toggle" style={{ position: 'absolute', bottom: 8, right: 16, zIndex: 2 }}>
        <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels?.(e.target.checked)} />
        Labels
      </label>
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
