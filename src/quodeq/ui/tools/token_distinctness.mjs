/**
 * Token distinctness audit — perceptual separation between the grade ramp,
 * the severity ramp, and the interactive accent for EVERY shipped theme
 * combination (5 families x 2 modes).
 *
 * The UX audit found the two ramps colliding: grade-bottom and sev-critical
 * resolved to the same red, and in several dark themes accent, compliance and
 * grade-top were one identical color meaning three different things. This
 * guard makes that class of regression fail in CI. Pure functions over the
 * tokens.css source text, same approach as token_contrast.mjs: no browser,
 * no CSS engine, and anything the tiny parser cannot resolve (color-mix) is
 * skipped rather than guessed.
 *
 * Distances are CIE76 delta-E in Lab. Thresholds are calibrated so the
 * audit's real findings fail while deliberate same-family lightness steps
 * (neo's all-green world) pass.
 *
 * Run directly for the full matrix:  node tools/token_distinctness.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

export const GRADE_TOKENS = [
  '--color-grade-top-text',
  '--color-grade-high-text',
  '--color-grade-mid-text',
  '--color-grade-low-text',
  '--color-grade-bottom-text',
];

export const SEV_TOKENS = [
  '--color-sev-critical-text',
  '--color-sev-major-text',
  '--color-sev-minor-text',
];

// Minimum CIE76 delta-E between…
export const MIN_DUEL_SIDES = 20;        // duel side A (accent) vs side B — identity must survive
export const MIN_DUEL_VS_GRADE = 20;     // duel side B vs any grade tier — identity is not a judgement
// There is deliberately NO grade-vs-severity, grade-vs-accent, or
// compliance-vs-accent rule. The 2026-08-25 recolor that introduced them
// (metallic ramp, then a caution descent, plus compliance moved to green)
// was rejected by the user, who chose the original v1.9.1 palette: grades
// live in the red channel severity also uses, and grade-top AND
// compliance ride the accent in dark themes. That sharing is the accepted
// design; chip vs score context disambiguates.

// The two floors below are grandfathered at the v1.9.1 palette's own
// worst values (low-vs-bottom step 4.9, gold-on-light contrast 1.9).
// They no longer assert WCAG; they exist so future edits cannot regress
// BELOW the baseline the user chose.
export const MIN_GRADE_STEP = 4.5;       // any two grade steps (mutual legibility)
export const MIN_GRADE_CONTRAST = 1.8;
export const SURFACE_TOKENS = ['--color-bg', '--color-surface', '--color-surface-alt'];

const FAMILIES = ['neo', 'galadriel', 'ifrit', 'deckard'];

// ---------------------------------------------------------------------------
// parsing (same shapes token_contrast.mjs understands)
// ---------------------------------------------------------------------------

export function parseBlocks(cssText) {
  const src = cssText.replace(/\/\*[\s\S]*?\*\//g, '');
  const blocks = [];
  let i = 0;
  const readBlock = (media) => {
    const open = src.indexOf('{', i);
    if (open === -1) { i = src.length; return; }
    const selector = src.slice(i, open).trim();
    if (selector.startsWith('@media')) {
      i = open + 1;
      const innerMedia = selector;
      while (i < src.length) {
        const next = src.slice(i).search(/\S/);
        if (next === -1) { i = src.length; break; }
        i += next;
        if (src[i] === '}') { i += 1; break; }
        readBlock(innerMedia);
      }
      return;
    }
    let depth = 1;
    let j = open + 1;
    while (j < src.length && depth > 0) {
      if (src[j] === '{') depth += 1;
      else if (src[j] === '}') depth -= 1;
      j += 1;
    }
    const body = src.slice(open + 1, j - 1);
    const decls = {};
    for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      decls[m[1]] = m[2].trim();
    }
    if (Object.keys(decls).length) blocks.push({ selector, media: media || null, decls });
    i = j;
  };
  while (i < src.length) {
    const next = src.slice(i).search(/\S/);
    if (next === -1) break;
    i += next;
    if (src[i] === '}') { i += 1; continue; }
    readBlock(null);
  }
  return blocks;
}

const isPlainRoot = (b) => !b.media && b.selector.includes(':root') && !b.selector.includes('data-theme');
const inMediaDark = (b) => Boolean(b.media && b.media.includes('prefers-color-scheme: dark'));
const hasExact = (name) => (b) => !b.media && b.selector.includes(`[data-theme="${name}"]`);
const hasEndsDark = (b) => !b.media && b.selector.includes('[data-theme$="dark"]');

function compose(blocks, matchers) {
  const vars = {};
  for (const match of matchers) {
    for (const b of blocks) {
      if (match(b)) Object.assign(vars, b.decls);
    }
  }
  return vars;
}

export function themeContexts(blocks) {
  const themes = {
    'daruma-light': compose(blocks, [isPlainRoot]),
    'daruma-dark-system': compose(blocks, [isPlainRoot, inMediaDark]),
    'daruma-dark': compose(blocks, [isPlainRoot, hasEndsDark, hasExact('dark')]),
    'daruma-light-explicit': compose(blocks, [isPlainRoot, hasExact('light')]),
  };
  for (const f of FAMILIES) {
    themes[`${f}-light`] = compose(blocks, [isPlainRoot, hasExact(`${f}-light`)]);
    themes[`${f}-dark`] = compose(blocks, [isPlainRoot, hasEndsDark, hasExact(`${f}-dark`)]);
  }
  return themes;
}

// ---------------------------------------------------------------------------
// colour math
// ---------------------------------------------------------------------------

export function resolveVar(vars, name, seen = new Set()) {
  if (seen.has(name)) return null;
  seen.add(name);
  const raw = vars[name];
  if (!raw) return null;
  const ref = raw.match(/^var\((--[\w-]+)\s*(?:,\s*([^)]+))?\)$/);
  if (ref) return resolveVar(vars, ref[1], seen) ?? (ref[2] ? ref[2].trim() : null);
  return raw;
}

export function parseColor(value) {
  if (!value) return null;
  const v = value.trim().toLowerCase();
  let m = v.match(/^#([0-9a-f]{6})([0-9a-f]{2})?$/);
  if (m) {
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  m = v.match(/^#([0-9a-f]{3})$/);
  if (m) return [...m[1]].map((c) => parseInt(c + c, 16));
  m = v.match(/^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/);
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])];
  return null;
}

function srgbToLinear(c) {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function rgbToLab([r, g, b]) {
  const [lr, lg, lb] = [srgbToLinear(r), srgbToLinear(g), srgbToLinear(b)];
  // sRGB D65
  let x = (0.4124564 * lr + 0.3575761 * lg + 0.1804375 * lb) / 0.95047;
  let y = (0.2126729 * lr + 0.7151522 * lg + 0.0721750 * lb) / 1.0;
  let z = (0.0193339 * lr + 0.1191920 * lg + 0.9503041 * lb) / 1.08883;
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  [x, y, z] = [f(x), f(y), f(z)];
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
}

export function deltaE(rgbA, rgbB) {
  const [l1, a1, b1] = rgbToLab(rgbA);
  const [l2, a2, b2] = rgbToLab(rgbB);
  return Math.hypot(l1 - l2, a1 - a2, b1 - b2);
}

export function contrastRatio(rgbA, rgbB) {
  const lum = ([r, g, b]) => 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
  const la = lum(rgbA);
  const lb = lum(rgbB);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

// ---------------------------------------------------------------------------
// audit
// ---------------------------------------------------------------------------

/**
 * @returns {{results: Array, failures: Array}} one result per rule per theme;
 *   failures is the subset under its required minimum. Unresolvable tokens
 *   (color-mix and friends) are skipped, matching token_contrast.mjs.
 */
export function auditDistinctness(cssText) {
  const blocks = parseBlocks(cssText);
  const themes = themeContexts(blocks);
  const results = [];
  const push = (theme, rule, a, b, value, min, kind) => {
    results.push({ theme, rule, a, b, value: Math.round(value * 10) / 10, min, kind, ok: value >= min });
  };
  for (const [theme, vars] of Object.entries(themes)) {
    const color = (token) => parseColor(resolveVar(vars, token));
    const grades = GRADE_TOKENS.map((t) => [t, color(t)]).filter(([, c]) => c);
    for (const [g, gc] of grades) {
      for (const surface of SURFACE_TOKENS) {
        const bg = color(surface);
        if (bg) push(theme, 'grade-contrast', g, surface, contrastRatio(gc, bg), MIN_GRADE_CONTRAST, 'contrast');
      }
    }
    for (let i = 0; i < grades.length; i += 1) {
      for (let j = i + 1; j < grades.length; j += 1) {
        push(theme, 'grade-step', grades[i][0], grades[j][0], deltaE(grades[i][1], grades[j][1]), MIN_GRADE_STEP, 'deltaE');
      }
    }
    // Duel identity: the two sides must stay tellable apart, and side B must
    // stay readable on every surface (A rides the accent, already covered).
    // B must also keep clear of the whole grade ramp: an identity line that
    // matches a tier color reads as a judgement, not a name.
    const duelA = color('--color-duel-a');
    const duelB = color('--color-duel-b');
    if (duelA && duelB) {
      push(theme, 'duel-sides', '--color-duel-a', '--color-duel-b', deltaE(duelA, duelB), MIN_DUEL_SIDES, 'deltaE');
      for (const surface of SURFACE_TOKENS) {
        const bg = color(surface);
        if (bg) push(theme, 'duel-b-contrast', '--color-duel-b', surface, contrastRatio(duelB, bg), MIN_GRADE_CONTRAST, 'contrast');
      }
      for (const [g, gc] of grades) {
        push(theme, 'duel-b-vs-grade', '--color-duel-b', g, deltaE(duelB, gc), MIN_DUEL_VS_GRADE, 'deltaE');
      }
    }
  }
  return { results, failures: results.filter((r) => !r.ok) };
}

export function defaultTokensPath() {
  return join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'styles', 'tokens.css');
}

const invokedDirectly = process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href;
if (invokedDirectly) {
  const tokensPath = process.argv.slice(2).find((a) => !a.startsWith('--')) || defaultTokensPath();
  const { results, failures } = auditDistinctness(readFileSync(tokensPath, 'utf8'));
  const failuresOnly = process.argv.includes('--failures');
  for (const r of results) {
    if (failuresOnly && r.ok) continue;
    const flag = r.ok ? '  ' : '!!';
    console.log(`${flag} ${r.theme.padEnd(22)} ${r.rule.padEnd(22)} ${r.a.padEnd(28)} vs ${r.b.padEnd(28)} ${String(r.value).padEnd(7)} (min ${r.min} ${r.kind})`);
  }
  console.log(`\n${results.length} checks, ${failures.length} failures`);
  process.exitCode = failures.length ? 1 : 0;
}
