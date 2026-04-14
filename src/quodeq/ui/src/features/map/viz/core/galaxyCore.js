/**
 * galaxyCore.js — Shared rendering engine for Galaxy visualizations.
 * Extracted from GalaxyView.jsx proven patterns.
 *
 * NOTE: This module requires a DOM environment (document.createElement,
 * getComputedStyle, MutationObserver). It is browser-only by design and
 * should not be imported in non-browser contexts (e.g. Node/SSR).
 * getThemeColors() accepts an optional sourceEl and cache parameter to
 * allow injection for testing.
 */

export const TAU = Math.PI * 2;

/* ── Theme color helpers ── */

export function parseCSSColor(cssColor) {
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
let _themeSourceEl = null;
let _themeObserver = null;
export function getThemeColors(sourceEl, { cache } = {}) {
  // When an injectable cache is provided (e.g. for testing), use it directly.
  if (cache) return cache;
  // Prefer previously-set source element (the .map-viz-container) so that
  // callers without an explicit element (scoreRGB, sevRGB) still read the
  // correct scoped CSS variables (e.g. .map-viz-dark overrides).
  const el = sourceEl || _themeSourceEl || document.documentElement;
  if (_themeColors && _themeSourceEl === el) return _themeColors;
  _themeSourceEl = el;
  const style = getComputedStyle(el);
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
  if (!_themeObserver) {
    _themeObserver = new MutationObserver(() => { _themeColors = null; });
    _themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
  }
  // Also watch the source element itself for class changes (e.g. map-viz-dark toggle)
  if (el !== document.documentElement && el._themeObs === undefined) {
    el._themeObs = new MutationObserver(() => { _themeColors = null; });
    el._themeObs.observe(el, { attributes: true, attributeFilter: ['class'] });
  }
  return _themeColors;
}

export function invalidateThemeColors() { _themeColors = null; }

// score is 0-10 scale (matching the app's grading system)
export function scoreRGB(score) {
  const tc = getThemeColors();
  if (score >= 9) return tc.gradeTop;
  if (score >= 7) return tc.gradeHigh;
  if (score >= 5) return tc.gradeMid;
  if (score >= 3) return tc.gradeLow;
  return tc.gradeBottom;
}

export function sevRGB(sev) {
  const tc = getThemeColors();
  return tc[sev] || tc.minor;
}

export function rgb(c) { return `rgb(${c.r},${c.g},${c.b})`; }
export function rgba(c, a) { return `rgba(${c.r},${c.g},${c.b},${a})`; }

/* ── Drawing helpers ── */

const GLOW_INNER_RATIO = 0.4;
const GLOW_OUTER_RATIO = 3;
const GLOW_CENTER_ALPHA = 0.15;
const GLOW_MID_ALPHA = 0.9;
const GLOW_EDGE_ALPHA = 0.6;

export function drawGlow(ctx, x, y, r, col, alpha) {
  if (r < 0.3 || alpha < 0.01) return;
  const { r: cr, g, b } = col;
  const gl = ctx.createRadialGradient(x, y, r * GLOW_INNER_RATIO, x, y, r * GLOW_OUTER_RATIO);
  gl.addColorStop(0, `rgba(${cr},${g},${b},${GLOW_CENTER_ALPHA * alpha})`);
  gl.addColorStop(1, `rgba(${cr},${g},${b},0)`);
  ctx.beginPath(); ctx.arc(x, y, r * GLOW_OUTER_RATIO, 0, TAU); ctx.fillStyle = gl; ctx.fill();
  const co = ctx.createRadialGradient(x, y, 0, x, y, r);
  co.addColorStop(0, `rgba(${Math.min(255, cr + 60)},${Math.min(255, g + 60)},${Math.min(255, b + 60)},${GLOW_MID_ALPHA * alpha})`);
  co.addColorStop(GLOW_EDGE_ALPHA, `rgba(${cr},${g},${b},${GLOW_EDGE_ALPHA * alpha})`);
  co.addColorStop(1, `rgba(${cr},${g},${b},${GLOW_CENTER_ALPHA * alpha})`);
  ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fillStyle = co; ctx.fill();
}

export function drawParticles(ctx, cx, cy, particles, scale, alpha, t, drawScale) {
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
}

/* ── Particles builder ── */

const MAX_PARTICLES_PER_SEV = 10;
const PARTICLE_ORBIT_OFFSET = 22;
const PARTICLE_ORBIT_RANGE = 28;
const PARTICLE_SPEED_BASE = 0.03;
const PARTICLE_SPEED_RANGE = 0.07;
const PARTICLE_SIZE_CRITICAL = 3.2;
const PARTICLE_SIZE_CRITICAL_RANGE = 0.8;
const PARTICLE_SIZE_MAJOR = 2.6;
const PARTICLE_SIZE_MAJOR_RANGE = 0.5;
const PARTICLE_SIZE_MINOR = 1.8;
const PARTICLE_SIZE_MINOR_RANGE = 0.5;
const PARTICLE_ECCENTRICITY_BASE = 0.65;
const PARTICLE_ECCENTRICITY_RANGE = 0.35;

export function mkParticles(critical, major, minor, baseRadius) {
  const ps = [];
  const add = (n, sev) => {
    const col = sevRGB(sev);
    for (let i = 0; i < Math.min(n, MAX_PARTICLES_PER_SEV); i++) {
      ps.push({
        col, sev,
        or: baseRadius + PARTICLE_ORBIT_OFFSET + Math.random() * PARTICLE_ORBIT_RANGE,
        os: (PARTICLE_SPEED_BASE + Math.random() * PARTICLE_SPEED_RANGE) * (Math.random() > 0.5 ? 1 : -1),
        op: Math.random() * TAU,
        sz: sev === 'critical' ? PARTICLE_SIZE_CRITICAL + Math.random() * PARTICLE_SIZE_CRITICAL_RANGE : sev === 'major' ? PARTICLE_SIZE_MAJOR + Math.random() * PARTICLE_SIZE_MAJOR_RANGE : PARTICLE_SIZE_MINOR + Math.random() * PARTICLE_SIZE_MINOR_RANGE,
        ec: PARTICLE_ECCENTRICITY_BASE + Math.random() * PARTICLE_ECCENTRICITY_RANGE,
        tp: Math.random() * TAU,
      });
    }
  };
  add(critical, 'critical');
  add(major, 'major');
  add(minor, 'minor');
  return ps;
}

/* ── Seeded PRNG ── */

export function seedHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return h;
}

const LCG_MULTIPLIER = 1664525;
const LCG_INCREMENT = 1013904223;
const LCG_MODULUS = 4294967296;

export function seededRng(seed) {
  let s = seed | 0;
  return () => {
    s = (s * LCG_MULTIPLIER + LCG_INCREMENT) | 0;
    return ((s >>> 0) / LCG_MODULUS);
  };
}

/* ── Grade helpers ── */

// Returns 0-10 scale to match scoreRGB thresholds
export function gradeToScore(grade) {
  return { A: 9.5, B: 8, C: 6.5, D: 4.5, F: 2 }[grade] || 5;
}

/* ── Constants ── */

export const LEGEND_ITEMS = [
  { color: 'var(--color-grade-top-text)', label: 'Exemplary' },
  { color: 'var(--color-grade-high-text)', label: 'Good' },
  { color: 'var(--color-grade-mid-text)', label: 'Adequate' },
  { color: 'var(--color-grade-low-text)', label: 'Poor' },
  { color: 'var(--color-grade-bottom-text)', label: 'Critical' },
];
