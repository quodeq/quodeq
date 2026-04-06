/**
 * galaxyCore.js — Shared rendering engine for Galaxy visualizations.
 * Extracted from GalaxyView.jsx proven patterns.
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
export function getThemeColors() {
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
  const obs = new MutationObserver(() => { _themeColors = null; });
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
  return _themeColors;
}

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

export function drawGlow(ctx, x, y, r, col, alpha) {
  if (r < 0.3 || alpha < 0.01) return;
  const { r: cr, g, b } = col;
  const gl = ctx.createRadialGradient(x, y, r * 0.4, x, y, r * 3);
  gl.addColorStop(0, `rgba(${cr},${g},${b},${0.15 * alpha})`);
  gl.addColorStop(1, `rgba(${cr},${g},${b},0)`);
  ctx.beginPath(); ctx.arc(x, y, r * 3, 0, TAU); ctx.fillStyle = gl; ctx.fill();
  const co = ctx.createRadialGradient(x, y, 0, x, y, r);
  co.addColorStop(0, `rgba(${Math.min(255, cr + 60)},${Math.min(255, g + 60)},${Math.min(255, b + 60)},${0.9 * alpha})`);
  co.addColorStop(0.6, `rgba(${cr},${g},${b},${0.6 * alpha})`);
  co.addColorStop(1, `rgba(${cr},${g},${b},${0.15 * alpha})`);
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

export function mkParticles(critical, major, minor, baseRadius) {
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

/* ── Seeded PRNG ── */

export function seedHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return h;
}

export function seededRng(seed) {
  let s = seed | 0;
  return () => {
    s = (s * 1664525 + 1013904223) | 0;
    return ((s >>> 0) / 4294967296);
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
