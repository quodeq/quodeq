/**
 * Shared tokens.css reader for the two token audits (token_contrast.mjs and
 * token_distinctness.mjs). Both walk the same stylesheet, build the same ten
 * theme contexts and resolve the same var()/hex/rgb shapes; only the metric
 * they then compute differs. This module is that common half, so a parser fix
 * lands in one place instead of two.
 *
 * Pure functions over the source text: no browser, no CSS engine. Anything
 * the parser cannot resolve (color-mix, named colours) yields null and the
 * caller skips it rather than guessing.
 */
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

export const SURFACE_TOKENS = ['--color-bg', '--color-surface', '--color-surface-alt'];

const FAMILIES = ['neo', 'galadriel', 'ifrit', 'deckard'];

// ---------------------------------------------------------------------------
// parsing
// ---------------------------------------------------------------------------

/**
 * Flatten tokens.css into blocks of { selector, media, decls } where decls
 * only keeps custom properties. Handles one level of @media nesting, which
 * is all tokens.css uses.
 *
 * @param {string} cssText
 * @returns {Array<{selector: string, media: string|null, decls: Record<string, string>}>}
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
 *
 * @param {ReturnType<typeof parseBlocks>} blocks
 * @returns {Record<string, Record<string, string>>} theme name -> custom props
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

/**
 * Follow a var() chain to a literal value, falling back to the var()'s own
 * default when the referenced name is undefined. Returns null on a cycle or
 * an undefined name with no fallback.
 *
 * @param {Record<string, string>} vars
 * @param {string} name
 * @param {Set<string>} [seen]
 * @returns {string|null}
 */
export function resolveVar(vars, name, seen = new Set()) {
  if (seen.has(name)) return null;
  seen.add(name);
  const raw = vars[name];
  if (!raw) return null;
  const ref = raw.match(/^var\((--[\w-]+)\s*(?:,\s*([^)]+))?\)$/);
  if (ref) return resolveVar(vars, ref[1], seen) ?? (ref[2] ? ref[2].trim() : null);
  return raw;
}

/**
 * Parse a hex or rgb()/rgba() colour into [r, g, b]. Anything exotic
 * (color-mix, named colours) returns null.
 *
 * @param {string|null|undefined} value
 * @returns {number[]|null}
 */
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

/**
 * One sRGB channel (0-255) to its linear-light value.
 *
 * @param {number} c
 * @returns {number}
 */
export function srgbToLinear(c) {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]) {
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

/**
 * WCAG contrast ratio between two [r, g, b] colours, order-independent.
 *
 * @param {number[]} rgbA
 * @param {number[]} rgbB
 * @returns {number}
 */
export function contrastRatio(rgbA, rgbB) {
  const la = luminance(rgbA);
  const lb = luminance(rgbB);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Absolute path of the shipped tokens.css both audits default to. */
export function defaultTokensPath() {
  return join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'styles', 'tokens.css');
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

/**
 * True when *moduleUrl* is the script node was asked to run, rather than an
 * import. Both audits are importable modules with a `node tools/x.mjs` mode.
 *
 * @param {string} moduleUrl the caller's import.meta.url
 * @returns {boolean}
 */
export function isDirectInvocation(moduleUrl) {
  return Boolean(process.argv[1]) && moduleUrl === new URL(`file://${process.argv[1]}`).href;
}

/**
 * Print an audit's rows (flagged `!!` when failing) and its tally, then set
 * the process exit code: 1 if anything failed, 0 otherwise.
 *
 * @param {{results: Array<{ok: boolean}>, failures: Array}} audit
 * @param {(row: object) => string} formatRow the audit-specific columns, after the flag
 * @param {{failuresOnly?: boolean}} [options] skip passing rows
 */
export function printAudit({ results, failures }, formatRow, { failuresOnly = false } = {}) {
  for (const r of results) {
    if (failuresOnly && r.ok) continue;
    console.log(`${r.ok ? '  ' : '!!'} ${formatRow(r)}`);
  }
  console.log(`\n${results.length} checks, ${failures.length} failures`);
  process.exitCode = failures.length ? 1 : 0;
}
