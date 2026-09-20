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

import { getGradeThresholds } from '../../../../utils/gradeThresholds.js';
import { DATA_THEME_ATTR } from '../../../../constants.js';

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

// Intentional module-level cache: stores parsed CSS theme colors to avoid
// repeated DOM reads on every frame. getThemeColors(sourceEl, { cache })
// provides an injection point for tests — pass a cache object to bypass
// the module-level singleton entirely.
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
    _themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', DATA_THEME_ATTR] });
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
const GRADE_COLOR_KEYS = ['gradeTop', 'gradeHigh', 'gradeMid', 'gradeLow'];

/**
 * @param {number} score
 * @param {{colors?: object, thresholds?: Array<[number, string]>}} [opts]
 *   Lazy defaults: an explicit `colors`/`thresholds` skips the DOM entirely
 *   (tests inject both); omitting them reads the live theme/thresholds
 *   exactly as before. Scene builders call this with no options — the
 *   default parameters preserve their existing (singleton-cache) behavior.
 */
export function scoreRGB(score, { colors = getThemeColors(), thresholds = getGradeThresholds() } = {}) {
  for (let i = 0; i < thresholds.length; i += 1) {
    if (score >= thresholds[i][0]) return colors[GRADE_COLOR_KEYS[i]] ?? colors.gradeLow;
  }
  return colors.gradeBottom;
}

/**
 * @param {string} sev
 * @param {{colors?: object}} [opts] Lazy default: an explicit `colors` skips
 *   the DOM entirely (tests inject it); omitting it reads the live theme.
 */
export function sevRGB(sev, { colors = getThemeColors() } = {}) {
  return colors[sev] || colors.minor;
}

export function rgb(c) { return `rgb(${c.r},${c.g},${c.b})`; }
export function rgba(c, a) { return `rgba(${c.r},${c.g},${c.b},${a})`; }

/* ── Drawing helpers ── */

const GLOW_INNER_RATIO = 0.4;
const GLOW_OUTER_RATIO = 3;
const GLOW_CENTER_ALPHA = 0.15;
const GLOW_MID_ALPHA = 0.9;
const GLOW_EDGE_ALPHA = 0.6;
// Below either floor the glow is invisible; skipping it saves two gradients
// per star per frame on a zoomed-out scene full of tiny stars.
const GLOW_MIN_RADIUS_PX = 0.3;
const GLOW_MIN_ALPHA = 0.01;
// The core gradient starts from a lightened copy of the colour, clamped to
// the top of the 8-bit channel range. Hoisted to module scope because
// drawGlow runs once per star per frame.
const CHANNEL_MAX = 255;
const GLOW_CORE_LIGHTEN = 60;
const lightenChannel = (c) => Math.min(CHANNEL_MAX, c + GLOW_CORE_LIGHTEN);

export function drawGlow(ctx, { x, y, r, col, alpha }) {
  if (r < GLOW_MIN_RADIUS_PX || alpha < GLOW_MIN_ALPHA) return;
  const { r: cr, g, b } = col;
  const gl = ctx.createRadialGradient(x, y, r * GLOW_INNER_RATIO, x, y, r * GLOW_OUTER_RATIO);
  gl.addColorStop(0, `rgba(${cr},${g},${b},${GLOW_CENTER_ALPHA * alpha})`);
  gl.addColorStop(1, `rgba(${cr},${g},${b},0)`);
  ctx.beginPath(); ctx.arc(x, y, r * GLOW_OUTER_RATIO, 0, TAU); ctx.fillStyle = gl; ctx.fill();
  const co = ctx.createRadialGradient(x, y, 0, x, y, r);
  co.addColorStop(0, `rgba(${lightenChannel(cr)},${lightenChannel(g)},${lightenChannel(b)},${GLOW_MID_ALPHA * alpha})`);
  co.addColorStop(GLOW_EDGE_ALPHA, `rgba(${cr},${g},${b},${GLOW_EDGE_ALPHA * alpha})`);
  co.addColorStop(1, `rgba(${cr},${g},${b},${GLOW_CENTER_ALPHA * alpha})`);
  ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fillStyle = co; ctx.fill();
}

// A particle breathes between base-amp and base+amp, paints a soft halo at
// HALO_RATIO times its own size, and is dropped once it is too small to see.
const PARTICLE_TWINKLE_BASE = 0.5;
const PARTICLE_TWINKLE_AMP = 0.08;
const PARTICLE_TWINKLE_SPEED = 0.5;
const PARTICLE_MIN_DRAW_SIZE_PX = 0.15;
const PARTICLE_HALO_RATIO = 3;
const PARTICLE_HALO_ALPHA = 0.12;
// The dot itself is drawn brighter than its twinkle alone would make it.
const PARTICLE_CORE_ALPHA_BOOST = 0.2;

export function drawParticles(ctx, particles, { cx, cy, scale, alpha, t, drawScale }) {
  const ds = drawScale ?? scale;
  particles.forEach(p => {
    const a = t * p.os + p.op;
    const px = cx + Math.cos(a) * p.or * p.ec * scale;
    const py = cy + Math.sin(a) * p.or * scale;
    const tw = PARTICLE_TWINKLE_BASE + PARTICLE_TWINKLE_AMP * Math.sin(t * PARTICLE_TWINKLE_SPEED + p.tp);
    const sz = p.sz * ds;
    if (sz < PARTICLE_MIN_DRAW_SIZE_PX) return;
    const { r, g, b } = p.col;
    ctx.beginPath(); ctx.arc(px, py, sz * PARTICLE_HALO_RATIO, 0, TAU);
    ctx.fillStyle = `rgba(${r},${g},${b},${tw * PARTICLE_HALO_ALPHA * alpha})`; ctx.fill();
    ctx.beginPath(); ctx.arc(px, py, sz, 0, TAU);
    ctx.fillStyle = `rgba(${r},${g},${b},${(tw + PARTICLE_CORE_ALPHA_BOOST) * alpha})`; ctx.fill();
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
// Midpoint of a 0..1 random sample: half the particles orbit anticlockwise.
const RNG_MIDPOINT = 0.5;

export function mkParticles(critical, major, minor, baseRadius) {
  const ps = [];
  const add = (n, sev) => {
    const col = sevRGB(sev);
    for (let i = 0; i < Math.min(n, MAX_PARTICLES_PER_SEV); i++) {
      ps.push({
        col, sev,
        or: baseRadius + PARTICLE_ORBIT_OFFSET + Math.random() * PARTICLE_ORBIT_RANGE,
        os: (PARTICLE_SPEED_BASE + Math.random() * PARTICLE_SPEED_RANGE) * (Math.random() > RNG_MIDPOINT ? 1 : -1),
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

/* ── Background starfield ── */

// Both galaxy views paint the same decorative starfield: positions are a
// fraction of the canvas, size and twinkle speed are seeded from these
// ranges. Nothing about a scene's layout depends on it.
const BG_STAR_COUNT = 120;
const BG_STAR_MAX_SIZE_PX = 1.2;
const BG_STAR_SPEED_MIN = 0.3;
const BG_STAR_SPEED_RANGE = 0.7;

/**
 * Build one background starfield.
 *
 * @param {Function} rand A 0..1 generator — a seeded RNG where the field
 *   must be stable across rebuilds, Math.random where it need not be.
 * @returns {Array<{x: number, y: number, sz: number, tw: number, sp: number}>}
 *   Stars, with x/y as fractions of the canvas and tw/sp the twinkle phase
 *   and speed.
 */
export function mkBackgroundStars(rand) {
  return Array.from({ length: BG_STAR_COUNT }, () => ({
    x: rand(), y: rand(),
    sz: rand() * BG_STAR_MAX_SIZE_PX,
    tw: rand() * TAU,
    sp: BG_STAR_SPEED_MIN + rand() * BG_STAR_SPEED_RANGE,
  }));
}

/* ── Seeded PRNG ── */

// `(h << 5) - h` is `h * 31`, the classic string-hash multiplier.
const SEED_HASH_SHIFT = 5;

export function seedHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << SEED_HASH_SHIFT) - h + str.charCodeAt(i)) | 0;
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

/**
 * The score a dimension or principle falls back to when the report carries
 * no usable number: the middle of the 0-10 scale, so it renders neither as a
 * success nor as a failure.
 */
export const NEUTRAL_SCORE = 5;

// Returns 0-10 scale to match scoreRGB thresholds
export function gradeToScore(grade) {
  return { A: 9.5, B: 8, C: 6.5, D: 4.5, F: 2 }[grade] || NEUTRAL_SCORE;
}

/* ── Constants ── */

export const LEGEND_ITEMS = [
  { color: 'var(--color-grade-top-text)', label: 'Exemplary' },
  { color: 'var(--color-grade-high-text)', label: 'Good' },
  { color: 'var(--color-grade-mid-text)', label: 'Adequate' },
  { color: 'var(--color-grade-low-text)', label: 'Poor' },
  { color: 'var(--color-grade-bottom-text)', label: 'Critical' },
];
