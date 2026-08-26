import { scoreColorClass } from '../utils/formatters.js';

/**
 * Shared helpers for the run/score history bar charts (Overview, History,
 * Explorer dimension panel). Centralises:
 *  - a memoised getComputedStyle reader for theme tokens
 *  - the bar fill mapping (score -> grade tier -> CSS variable)
 *  - reference-line positions and chart margins reused across charts
 */

const _cssVarCache = new Map();

export function cssVar(name, fallback = '') {
  if (_cssVarCache.has(name)) return _cssVarCache.get(name);
  if (typeof document === 'undefined') return fallback;
  const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const result = val || fallback;
  _cssVarCache.set(name, result);
  return result;
}

/** Clear the cache; called automatically on theme change, exported for tests. */
export function clearCssVarCache() { _cssVarCache.clear(); }

if (typeof document !== 'undefined') {
  new MutationObserver(() => _cssVarCache.clear()).observe(
    document.documentElement,
    { attributes: true, attributeFilter: ['data-theme'] },
  );
}

const GRADE_CSS_VARS = {
  'grade-top':    '--color-grade-top-text',
  'grade-high':   '--color-grade-high-text',
  'grade-mid':    '--color-grade-mid-text',
  'grade-low':    '--color-grade-low-text',
  'grade-bottom': '--color-grade-bottom-text',
  'grade-none':   '--color-text-muted',
};

/** Bar color follows the active theme's grade spectrum. */
export function scoreBarColor(score) {
  const varName = GRADE_CSS_VARS[scoreColorClass(score)] || '--color-accent';
  return cssVar(varName);
}

/**
 * Adaptive Y domain for the score charts. Real projects live in a narrow
 * band (say 6.9-8.2), and a fixed 0-10 axis flattens the trend into a
 * near-straight line riding on top of near-full, near-equal bars. Padding
 * the data range by half a point keeps the shape visible while no bar ever
 * renders empty (the floor sits below the lowest score) or full (the
 * ceiling sits above the highest).
 */
export function scoreDomain(values) {
  const valid = (values || []).filter((n) => Number.isFinite(n));
  if (!valid.length) return [0, 10];
  const lo = Math.max(0, Math.floor(Math.min(...valid) - 0.5));
  const hi = Math.min(10, Math.ceil(Math.max(...valid) + 0.5));
  return [lo, hi > lo ? hi : lo + 1];
}

/** Reference-line ticks: domain bounds plus quarter divisions of the range. */
export function refLineValues([lo, hi]) {
  const step = (hi - lo) / 4;
  return [lo, lo + step, lo + 2 * step, lo + 3 * step, hi];
}

/** Margin zeroed so bars span edge-to-edge inside the panel body. */
export const CHART_MARGIN = { top: 8, right: 0, bottom: 0, left: 0 };

/** Opacity for the selected vs deselected bars across all score charts. */
export const SELECTED_BAR_OPACITY = 0.85;
export const DESELECTED_BAR_OPACITY = 0.4;

/** Fixed chart height for the History tab's score chart (HistoryChartPanel),
 * shared with its Suspense placeholder so the two never drift apart. */
export const HISTORY_CHART_HEIGHT = 220;
