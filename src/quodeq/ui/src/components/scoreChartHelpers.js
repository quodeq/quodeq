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

/** Reference-line ticks at 25% / 50% / 75% of the 0-10 score range. */
export const REF_LINE_LOW = 2.5;
export const REF_LINE_MID = 5;
export const REF_LINE_HIGH = 7.5;

/** Margin zeroed so bars span edge-to-edge inside the panel body. */
export const CHART_MARGIN = { top: 8, right: 0, bottom: 0, left: 0 };

/** Opacity for the selected vs deselected bars across all score charts. */
export const SELECTED_BAR_OPACITY = 0.85;
export const DESELECTED_BAR_OPACITY = 0.4;
