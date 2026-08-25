/**
 * Token contrast audit — WCAG contrast of the text tokens against the
 * surface tokens for EVERY shipped theme combination (5 families x 2 modes).
 *
 * The UX audit's headline finding was that only the default pair ever gets
 * eyeballed while ten combinations ship; this makes the other eight fail in
 * CI instead of in a user's screenshot. Pure functions over the tokens.css
 * source text — no browser, no CSS engine. The parser understands exactly
 * the shapes tokens.css uses (custom props, var() chains, hex/rgb colours,
 * one level of @media nesting); anything fancier (color-mix) is skipped.
 *
 * Run directly for the full matrix:  node tools/token_contrast.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

// Text tokens audited, with the minimum ratio each must hit against every
// surface it can sit on. --color-text and --color-text-muted carry real
// copy (body, labels, secondary text) -> WCAG AA normal-text 4.5. subtle is
// pinned at 3.0: it is documented for decorative/tertiary use, but it still
// ends up on timestamps and captions, so it must at least clear the
// large-text/UI-component floor.
export const TEXT_REQUIREMENTS = {
  '--color-text': 4.5,
  '--color-text-muted': 4.5,
  '--color-text-subtle': 3.0,
};

export const SURFACE_TOKENS = ['--color-bg', '--color-surface', '--color-surface-alt'];

const FAMILIES = ['neo', 'galadriel', 'ifrit', 'deckard'];

// ---------------------------------------------------------------------------
// parsing
// ---------------------------------------------------------------------------

/**
 * Flatten tokens.css into blocks of { selector, media, decls } where decls
 * only keeps custom properties. Handles one level of @media nesting, which
 * is all tokens.css uses.
 */
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

/** Merge every matching block's declarations, in file order per matcher order. */
function compose(blocks, matchers) {
  const vars = {};
  for (const match of matchers) {
    for (const b of blocks) {
      if (match(b)) Object.assign(vars, b.decls);
    }
  }
  return vars;
}

/**
 * The ten shipped combinations. Daruma is the default family: its light
 * mode is the bare :root, its dark mode exists twice (system-preference
 * media block, and the explicit data-theme="dark" the toggle sets).
 */
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
  return null; // color-mix, named colours, anything exotic
}

function luminance([r, g, b]) {
  const chan = (c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b);
}

export function contrastRatio(rgbA, rgbB) {
  const la = luminance(rgbA);
  const lb = luminance(rgbB);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

// ---------------------------------------------------------------------------
// audit
// ---------------------------------------------------------------------------

/**
 * @returns {{results: Array, failures: Array}} one result per
 *   theme x text-token x surface-token with the measured ratio; failures is
 *   the subset under its required minimum.
 */
export function auditContrast(cssText) {
  const blocks = parseBlocks(cssText);
  const themes = themeContexts(blocks);
  const results = [];
  for (const [theme, vars] of Object.entries(themes)) {
    for (const [textToken, min] of Object.entries(TEXT_REQUIREMENTS)) {
      const fg = parseColor(resolveVar(vars, textToken));
      if (!fg) continue;
      for (const surfaceToken of SURFACE_TOKENS) {
        const bg = parseColor(resolveVar(vars, surfaceToken));
        if (!bg) continue;
        const ratio = Math.round(contrastRatio(fg, bg) * 100) / 100;
        results.push({
          theme, textToken, surfaceToken, min, ratio,
          fg: resolveVar(vars, textToken), bg: resolveVar(vars, surfaceToken),
          ok: ratio >= min,
        });
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
  const { results, failures } = auditContrast(readFileSync(defaultTokensPath(), 'utf8'));
  for (const r of results) {
    const flag = r.ok ? '  ' : '!!';
    console.log(`${flag} ${r.theme.padEnd(22)} ${r.textToken.padEnd(22)} on ${r.surfaceToken.padEnd(20)} ${String(r.ratio).padEnd(6)} (min ${r.min})  ${r.fg} / ${r.bg}`);
  }
  console.log(`\n${results.length} checks, ${failures.length} failures`);
  process.exitCode = failures.length ? 1 : 0;
}
