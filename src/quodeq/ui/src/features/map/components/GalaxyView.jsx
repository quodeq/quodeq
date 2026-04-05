import { useRef, useEffect, useMemo, useCallback, useState } from 'react';
import { complianceRateColor } from '../utils/mapColors.js';

const TAU = Math.PI * 2;

function parseCSSColor(cssColor) {
  // Parse any CSS color string to {r,g,b} via a temporary canvas
  if (!parseCSSColor._ctx) {
    const c = document.createElement('canvas');
    c.width = c.height = 1;
    parseCSSColor._ctx = c.getContext('2d');
  }
  const ctx = parseCSSColor._ctx;
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = cssColor;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return { r, g, b };
}

let _themeColors = null;
function getThemeColors() {
  if (_themeColors) return _themeColors;
  const style = getComputedStyle(document.documentElement);
  const get = (v) => parseCSSColor(style.getPropertyValue(v).trim() || '#888');
  const raw = (v) => style.getPropertyValue(v).trim();
  _themeColors = {
    critical: get('--color-sev-critical-text'),
    major: get('--color-sev-major-text'),
    minor: get('--color-sev-minor-text'),
    compliance: get('--color-compliance'),
    gradeTop: get('--color-grade-top-text'),
    gradeHigh: get('--color-grade-high-text'),
    gradeMid: get('--color-grade-mid-text'),
    gradeLow: get('--color-grade-low-text'),
    gradeBottom: get('--color-grade-bottom-text'),
    bg: raw('--color-bg') || '#0a0a16',
    bgAlt: raw('--color-surface-alt') || '#12122a',
    text: get('--color-text'),
    textMuted: get('--color-text-muted'),
    border: get('--color-border'),
    surface: raw('--color-surface') || '#1a1a2e',
  };
  // Invalidate on theme change (class changes on root)
  const obs = new MutationObserver(() => { _themeColors = null; });
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
  return _themeColors;
}

// score is 0-10 scale (matching the app's grading system)
function scoreRGB(score) {
  const tc = getThemeColors();
  if (score >= 9) return tc.gradeTop;
  if (score >= 7) return tc.gradeHigh;
  if (score >= 5) return tc.gradeMid;
  if (score >= 3) return tc.gradeLow;
  return tc.gradeBottom;
}

// Returns 0-10 scale to match scoreRGB thresholds
function gradeToScore(grade) {
  return { A: 9.5, B: 8, C: 6.5, D: 4.5, F: 2 }[grade] || 5;
}

function sevRGB(sev) {
  const tc = getThemeColors();
  return tc[sev] || tc.minor;
}

function rgb(c) { return `rgb(${c.r},${c.g},${c.b})`; }
function rgba(c, a) { return `rgba(${c.r},${c.g},${c.b},${a})`; }

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

function mkParticles(critical, major, minor, baseRadius) {
  const ps = [];
  const add = (n, sev) => {
    const col = sevRGB(sev);
    for (let i = 0; i < Math.min(n, 10); i++) {
      ps.push({
        col, sev,
        or: baseRadius + 22 + Math.random() * 28,
        os: (0.03 + Math.random() * 0.07) * (Math.random() > 0.5 ? 1 : -1),
        op: Math.random() * TAU,
        sz: sev === 'critical' ? 3.2 + Math.random() * 0.8 : sev === 'major' ? 2.6 + Math.random() * 0.5 : 1.8 + Math.random() * 0.5,
        ec: 0.65 + Math.random() * 0.35,
        tp: Math.random() * TAU,
      });
    }
  };
  add(critical, 'critical');
  add(major, 'major');
  add(minor, 'minor');
  return ps;
}

const CONSTELLATION_LABELS = {
  builtin: 'ISO Standards', quodeq: 'Quodeq Standards', community: 'Community Standards', custom: 'Custom Standards', _default: '',
};

function buildScene(dimensions, W, H, standardTypes) {
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

  const spread = Math.min(W, H) * 0.35;
  // Scale cluster spread based on star count — more stars need more space
  const baseClusterSpread = Math.min(W, H) * 0.16;

  if (useConstellations) {
    // Organic layout positions — hand-tuned for 1-4 groups, avoids overlap
    const layouts = {
      1: [[0, 0]],
      2: [[-0.55, -0.1], [0.55, 0.15]],
      3: [[-0.6, -0.35], [0.55, -0.15], [-0.05, 0.55]],
      4: [[-0.6, -0.4], [0.55, -0.3], [-0.45, 0.5], [0.6, 0.5]],
    };
    const n = groupKeys.length;
    const positions = layouts[Math.min(n, 4)] || layouts[4];
    groupKeys.forEach((type, gi) => {
      const [px, py] = positions[gi % positions.length];
      const clusterCx = px * spread * 1.8;
      const clusterCy = py * spread * 1.8;
      const groupDims = dimGroups[type];
      const clusterSpread = baseClusterSpread + groupDims.length * 12;

      const startIdx = globalIdx;
      const lines = [];

      // Place stars with minimum spacing — use golden angle for even distribution
      const goldenAngle = TAU * (1 - 1 / 1.618);
      groupDims.forEach((dim, i) => {
        const totalV = dim.totals?.violationCount || dim.violations?.length || 0;
        const totalC = dim.totals?.complianceCount || dim.compliance?.length || 0;
        const score = dim.overallScore ? parseFloat(dim.overallScore) : 5;
        const radius = 3 + Math.sqrt(totalV + totalC) * 0.4;
        // Golden angle spiral for even spacing
        const a = i * goldenAngle;
        const dist = clusterSpread * (0.4 + (i / Math.max(1, groupDims.length - 1)) * 0.6);
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
          pp: Math.random() * TAU,
          x: 0, y: 0,
          principleCount: 0,
          _raw: dim,
        });
        // Connect to previous star in cluster
        if (i > 0) lines.push({ a: startIdx + i - 1, b: startIdx + i });
        globalIdx++;
      });
      // Close the shape for 3+ stars
      if (groupDims.length >= 3) lines.push({ a: startIdx + groupDims.length - 1, b: startIdx });

      constellations.push({ type, label: CONSTELLATION_LABELS[type] || type, cx: clusterCx, cy: clusterCy, spread: clusterSpread, lines });
    });
  } else {
    // Single group — original circular layout
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
        j: (Math.random() - 0.5) * 40,
        _clusterCx: 0, _clusterCy: 0, _ox: 0, _oy: 0,
        pp: Math.random() * TAU,
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
        od: 25 + (pi / (prinList.length || 1)) * 35 + Math.random() * 5,
        pp: Math.random() * TAU,
        ...sev,
        x: 0, y: 0,
        particles: mkParticles(sev.critical, sev.major, sev.minor, radius),
        _rawViolations: p.violations,
        _rawCompliance: p.compliance,
        dimParticle: {
          col: scoreRGB(pScore),
          or: 12 + Math.sqrt(pv + pc) * 1.5,
          os: (0.02 + Math.random() * 0.05) * (Math.random() > 0.5 ? 1 : -1),
          op: Math.random() * TAU,
          sz: 0.8 + Math.sqrt(pv + pc) * 0.15,
          ec: 0.9 + Math.random() * 0.1,
          tp: Math.random() * TAU,
        },
      };
    });
  });

  stars.forEach((s, i) => { s.principleCount = (principles[i] || []).length; });

  // Connections between dimensions that share files
  const dimFiles = dimensions.map(d => new Set((d.violations || []).map(v => v.file).filter(Boolean)));
  const connections = [];
  for (let i = 0; i < dimensions.length; i++) {
    for (let j = i + 1; j < dimensions.length; j++) {
      let shared = 0;
      dimFiles[i].forEach(f => { if (dimFiles[j].has(f)) shared++; });
      if (shared > 0) {
        const maxFiles = Math.max(dimFiles[i].size, dimFiles[j].size, 1);
        connections.push({ a: i, b: j, s: Math.min(1, shared / maxFiles) });
      }
    }
  }

  const bg = Array.from({ length: 120 }, () => ({
    x: Math.random(), y: Math.random(),
    sz: Math.random() * 1.2,
    tw: Math.random() * TAU,
    sp: 0.3 + Math.random() * 0.7,
  }));

  return { stars, principles, connections, constellations, bg };
}

const LEGEND_ITEMS = [
  { color: 'var(--color-grade-top-text)', label: 'Exemplary' },
  { color: 'var(--color-grade-high-text)', label: 'Good' },
  { color: 'var(--color-grade-mid-text)', label: 'Adequate' },
  { color: 'var(--color-grade-low-text)', label: 'Poor' },
  { color: 'var(--color-grade-bottom-text)', label: 'Critical' },
];

// Module-level saved state — persists across unmount/remount (back from detail)
let _savedGalaxyNav = null;
let _savedGalaxyCam = null;

export default function GalaxyView({ dimensions, onNavigate, showLabels = true, setShowLabels, resetKey = 0, projectName = '' }) {
  const canvasRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  // Fetch standard types for constellation grouping
  const [standardTypes, setStandardTypes] = useState({});
  useEffect(() => {
    import('../../../api/standards.js').then(({ listStandards }) => {
      listStandards().then(stds => {
        const map = {};
        stds.forEach(s => { map[(s.id || '').toLowerCase()] = s.type || 'custom'; });
        setStandardTypes(map);
      });
    }).catch(() => {});
  }, []);

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

  // Get camera target for current depth
  const getTarget = useCallback(() => {
    const nav = navRef.current;
    if (nav.depth === 0) {
      if (nav.clusterCx != null) return { x: size.w / 2 + nav.clusterCx, y: size.h / 2 + nav.clusterCy, z: 2.5 };
      return { x: size.w / 2, y: size.h / 2, z: 1 };
    }
    if (nav.depth === 1 && nav.dim !== null) { const s = scene.stars[nav.dim]; return { x: s.x, y: s.y, z: 5 }; }
    if (nav.depth === 2 && nav.dim !== null && nav.prin !== null) { const p = scene.principles[nav.dim][nav.prin]; return { x: p.x, y: p.y, z: 50 }; }
    return camRef.current;
  }, [scene, size.w, size.h]);

  // Drawing helpers
  const drawGlow = useCallback((ctx, sx, sy, sr, col, alpha) => {
    if (sr < 0.3 || alpha < 0.01) return;
    const { r, g, b } = col;
    const gl = ctx.createRadialGradient(sx, sy, sr * 0.4, sx, sy, sr * 3);
    gl.addColorStop(0, `rgba(${r},${g},${b},${0.15 * alpha})`);
    gl.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.beginPath(); ctx.arc(sx, sy, sr * 3, 0, TAU); ctx.fillStyle = gl; ctx.fill();
    const co = ctx.createRadialGradient(sx, sy, 0, sx, sy, sr);
    co.addColorStop(0, `rgba(${Math.min(255, r + 60)},${Math.min(255, g + 60)},${Math.min(255, b + 60)},${0.9 * alpha})`);
    co.addColorStop(0.6, `rgba(${r},${g},${b},${0.6 * alpha})`);
    co.addColorStop(1, `rgba(${r},${g},${b},${0.15 * alpha})`);
    ctx.beginPath(); ctx.arc(sx, sy, sr, 0, TAU); ctx.fillStyle = co; ctx.fill();
  }, []);

  const drawParticles = useCallback((ctx, cx, cy, particles, scale, alpha, t, drawScale) => {
    const ds = drawScale ?? scale;
    particles.forEach(p => {
      const a = t * p.os + p.op;
      const px = cx + Math.cos(a) * p.or * p.ec * scale;
      const py = cy + Math.sin(a) * p.or * scale;
      const tw = 0.5 + 0.08 * Math.sin(t * 0.5 + p.tp);
      const sz = p.sz * ds;
      if (sz < 0.15) return;
      const { r, g, b } = p.col;
      ctx.beginPath(); ctx.arc(px, py, sz * 3, 0, TAU);
      ctx.fillStyle = `rgba(${r},${g},${b},${tw * 0.12 * alpha})`; ctx.fill();
      ctx.beginPath(); ctx.arc(px, py, sz, 0, TAU);
      ctx.fillStyle = `rgba(${r},${g},${b},${(tw + 0.2) * alpha})`; ctx.fill();
    });
  }, []);

  // --- Main animation loop ---
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !scene) return;
    const ctx = canvas.getContext('2d');
    let running = true;

    function frame() {
      if (!running) return;
      const t = timeRef.current += 0.016;
      const nav = navRef.current;
      const W = size.w, H = size.h;
      // Initialize camera at canvas center on first frame
      if (!camRef.current) camRef.current = { x: W / 2, y: H / 2, z: 1 };
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
          // Dashed constellation lines between stars
          con.lines.forEach(l => {
            const sa = w2s(scene.stars[l.a].x, scene.stars[l.a].y);
            const sb = w2s(scene.stars[l.b].x, scene.stars[l.b].y);
            const cmx = (sa.x + sb.x) / 2 + (sa.y - sb.y) * 0.1;
            const cmy = (sa.y + sb.y) / 2 + (sb.x - sa.x) * 0.1;
            ctx.beginPath(); ctx.moveTo(sa.x, sa.y); ctx.quadraticCurveTo(cmx, cmy, sb.x, sb.y);
            ctx.strokeStyle = `rgba(${mr},${mg},${mb},${0.4 * conAlpha * conClusterDim})`;
            ctx.lineWidth = 0.8;
            ctx.setLineDash([3, 5]); ctx.stroke(); ctx.setLineDash([]);
          });
          // Constellation label
          if (showLabels && con.label) {
            const lsc = w2s(W / 2 + con.cx, H / 2 + con.cy - con.spread - 20);
            ctx.font = '600 14px -apple-system,BlinkMacSystemFont,sans-serif';
            ctx.textAlign = 'center';
            ctx.fillStyle = `rgba(${mr},${mg},${mb},${0.55 * conAlpha * conClusterDim})`;
            ctx.fillText(con.label, lsc.x, lsc.y);
            // Store screen position for click detection
            con._lx = lsc.x; con._ly = lsc.y;
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
          ctx.textAlign = 'center'; ctx.fillStyle = rgba(s.col, 0.9 * labelAlpha);
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
            ctx.textAlign = 'center'; ctx.fillStyle = rgba(p.col, la);
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
  }, [scene, size, showLabels, w2s, getTarget, drawGlow, drawParticles]);

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
    const row = (label, value) => `<div style="display:flex;justify-content:space-between;gap:12px;color:var(--color-text-muted)"><span>${label}</span><span style="color:var(--color-text);font-weight:500">${value}</span></div>`;
    const rows = [row('Score', d.score.toFixed(1))];
    if (h.type === 'dim') rows.push(row('Principles', d.principleCount));
    rows.push(row('Violations', d.violations), row('Compliance', d.compliance));
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
      return {
        title: clusterCon?.label || (projectName ? `${projectName} System` : 'Project System'),
        lines: [
          { label: 'Score', value: avgScore.toFixed(1) },
          { label: 'Dimensions', value: clusterStars.length },
          { label: 'Violations', value: totalV },
          { label: 'Compliance', value: totalC },
        ],
        hint: 'Click a dimension to explore',
        detailAction: null,
      };
    }
    if (nav.depth === 1 && nav.dim !== null) {
      const dim = scene.stars[nav.dim];
      const prins = scene.principles[nav.dim] || [];
      const rawDim = dim._raw;
      return {
        title: dim.name,
        lines: [
          { label: 'Score', value: dim.score.toFixed(1) },
          { label: 'Principles', value: prins.length },
          { label: 'Violations', value: dim.violations },
          { label: 'Compliance', value: dim.compliance },
        ],
        hint: 'Click a principle to explore',
        detailAction: () => {
          const d = scene.stars[navRef.current.dim]?._raw;
          if (!d) return;
          onNavigate?.('explorer', { dimension: d.dimension, runId: d.fromRunId, dateLabel: d.fromDateLabel, sourceTab: 'map' });
        },
      };
    }
    if (nav.depth === 2 && nav.dim !== null && nav.prin !== null) {
      const prin = scene.principles[nav.dim][nav.prin];
      return {
        title: prin.name,
        lines: [
          { label: 'Score', value: prin.score.toFixed(1) },
          { label: 'Violations', value: prin.violations },
          { label: 'Compliance', value: prin.compliance },
        ],
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
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, margin: '3px 0', color: 'var(--color-text-muted)' }}>
              <span>{l.label}</span>
              <span style={{ color: 'var(--color-text)', fontWeight: 500 }}>{l.value}</span>
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

export { scoreRGB, sevRGB, rgb, rgba, gradeToScore };
