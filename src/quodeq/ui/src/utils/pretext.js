/**
 * Thin wrapper around `@chenglou/pretext` for off-DOM text measurement.
 *
 * Why: quodeq has several long, wrap-sensitive text blocks — finding REASON
 * and DETAIL paragraphs, violation titles, file:line cells. Pretext computes
 * the rendered height and line count at a given width without touching the
 * DOM, so callers (currently just `usePretextHeight`, later a virtualiser)
 * can know heights before paint and avoid layout thrash.
 *
 * Caching: `prepare()` is the expensive step (text segmentation, canvas
 * measurement). We memoise it by `font|text` — identical inputs reuse the
 * same PreparedText. Cache is module-level and bounded by
 * `PREPARE_CACHE_LIMIT` using a simple FIFO eviction; size is deliberately
 * generous because prepared objects are small, and we'd rather retain a
 * warm cache across HMR updates than recompute.
 */
import {
  prepare as pretextPrepare,
  layout as pretextLayout,
  prepareWithSegments,
  measureNaturalWidth,
} from '@chenglou/pretext';

const PREPARE_CACHE_LIMIT = 1024;
const _prepareCache = new Map();

function cacheKey(text, font) {
  return `${font}\u0000${text}`;
}

/**
 * Memoised `prepare`. Pass the same `(text, font)` pair and you get the
 * same cached PreparedText back.
 * @param {string} text
 * @param {string} font - CSS font shorthand (e.g. `"13px JetBrains Mono"`).
 * @returns {object} PreparedText from @chenglou/pretext
 */
export function prepare(text, font) {
  const key = cacheKey(text, font);
  const cached = _prepareCache.get(key);
  if (cached) return cached;
  const prepared = pretextPrepare(text, font);
  if (_prepareCache.size >= PREPARE_CACHE_LIMIT) {
    // Drop oldest entry — Map preserves insertion order.
    const oldest = _prepareCache.keys().next().value;
    if (oldest !== undefined) _prepareCache.delete(oldest);
  }
  _prepareCache.set(key, prepared);
  return prepared;
}

/**
 * Measure height + line count of `text` rendered in `font` at `maxWidth` px,
 * with `lineHeight` px per line.
 *
 * @param {string} text
 * @param {string} font
 * @param {number} maxWidth
 * @param {number} lineHeight
 * @returns {{ height: number, lineCount: number }}
 */
export function measureText(text, font, maxWidth, lineHeight) {
  if (!text || maxWidth <= 0 || lineHeight <= 0) return { height: 0, lineCount: 0 };
  const prepared = prepare(text, font);
  const result = pretextLayout(prepared, maxWidth, lineHeight);
  return { height: result.height, lineCount: result.lineCount };
}

/**
 * Clear the prepare cache. Exported for tests and theme-change handlers
 * (the cache is keyed on font string, so font-family changes naturally
 * invalidate themselves — this is only needed if callers know they've
 * introduced a measurement-invalidating change).
 */
export function clearPrepareCache() {
  _prepareCache.clear();
  _segmentCache.clear();
}

/**
 * Measure the natural (unwrapped) width of a single-line text.
 * Uses a cached `prepareWithSegments` under the hood since `measureNaturalWidth`
 * needs the segmented form.
 *
 * @param {string} text
 * @param {string} font
 * @returns {number} width in px
 */
const _segmentCache = new Map();
const SEGMENT_CACHE_LIMIT = 512;
function prepareSegments(text, font) {
  const key = cacheKey(text, font);
  const cached = _segmentCache.get(key);
  if (cached) return cached;
  const prepared = prepareWithSegments(text, font);
  if (_segmentCache.size >= SEGMENT_CACHE_LIMIT) {
    const oldest = _segmentCache.keys().next().value;
    if (oldest !== undefined) _segmentCache.delete(oldest);
  }
  _segmentCache.set(key, prepared);
  return prepared;
}

export function measureWidth(text, font) {
  if (!text) return 0;
  return measureNaturalWidth(prepareSegments(text, font));
}

/**
 * Fit `text` to `maxWidth` using middle truncation. If the text already fits,
 * returns it unchanged. Otherwise keeps as much leading and trailing context
 * as possible around an `ellipsis` marker in the middle.
 *
 * Example:
 *   fitMiddleTruncate('auth/very/deep/jwt.py:42', font, 120)
 *   // → 'auth/…/jwt.py:42'
 *
 * Uses binary search over the split point, so worst-case cost is
 * O(log n · measureWidth) per call. Results with identical inputs hit the
 * prepare cache.
 *
 * @param {string} text
 * @param {string} font
 * @param {number} maxWidth - Container width in px.
 * @param {string} [ellipsis='…']
 * @returns {string}
 */
/**
 * Fit `text` to `maxWidth` using end truncation. Preserves the leading
 * characters and drops the tail behind an ellipsis. Use this when the head
 * of the string is the informative part (e.g. a comma-separated list where
 * the first items are most important).
 *
 * @param {string} text
 * @param {string} font
 * @param {number} maxWidth
 * @param {string} [ellipsis='…']
 * @returns {string}
 */
export function fitEndTruncate(text, font, maxWidth, ellipsis = '\u2026') {
  if (!text || maxWidth <= 0) return text;
  if (measureWidth(text, font) <= maxWidth) return text;

  const ellipsisWidth = measureWidth(ellipsis, font);
  if (ellipsisWidth > maxWidth) return ellipsis;

  const n = text.length;
  let lo = 0;
  let hi = n - 1;
  let best = ellipsis;
  while (lo <= hi) {
    const keep = (lo + hi) >> 1;
    const candidate = text.slice(0, keep) + ellipsis;
    if (measureWidth(candidate, font) <= maxWidth) {
      best = candidate;
      lo = keep + 1;
    } else {
      hi = keep - 1;
    }
  }
  return best;
}

export function fitMiddleTruncate(text, font, maxWidth, ellipsis = '\u2026') {
  if (!text || maxWidth <= 0) return text;
  if (measureWidth(text, font) <= maxWidth) return text;

  const ellipsisWidth = measureWidth(ellipsis, font);
  if (ellipsisWidth > maxWidth) return ellipsis;

  const n = text.length;
  // Binary search on number of visible characters preserved.
  // Keep roughly equal halves; bias to the tail so the line:column stays
  // visible for file refs like 'a/b/c/file.py:42'.
  let lo = 1;
  let hi = n - 1;
  let best = ellipsis;
  while (lo <= hi) {
    const keep = (lo + hi) >> 1;
    // Favour the tail by 1 char when total is odd.
    const tail = Math.ceil(keep / 2);
    const head = keep - tail;
    const candidate = text.slice(0, head) + ellipsis + text.slice(n - tail);
    if (measureWidth(candidate, font) <= maxWidth) {
      best = candidate;
      lo = keep + 1;
    } else {
      hi = keep - 1;
    }
  }
  return best;
}

/**
 * Build a CSS-font-shorthand string that matches what the browser will use.
 * Pass the element (or any DescendantElement) whose computed style you want
 * to mirror. Falls back to a mono stack when passed `null`/`undefined`.
 *
 * @param {Element | null | undefined} el
 * @returns {string}
 */
export function cssFontFromElement(el) {
  const DEFAULT = '13px "JetBrains Mono", ui-monospace, monospace';
  if (!el || typeof window === 'undefined') return DEFAULT;
  const cs = window.getComputedStyle(el);
  const size = cs.fontSize || '13px';
  const family = cs.fontFamily || '"JetBrains Mono", ui-monospace, monospace';
  const weight = cs.fontWeight && cs.fontWeight !== '400' ? `${cs.fontWeight} ` : '';
  const style = cs.fontStyle && cs.fontStyle !== 'normal' ? `${cs.fontStyle} ` : '';
  return `${style}${weight}${size} ${family}`.trim();
}
