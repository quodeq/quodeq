/**
 * Tooltip DOM writes shared by the galaxy and folder canvases.
 *
 * Both canvases build their own tooltip markup (different rows, different
 * escaping rules) but show it the same way and list severities the same way,
 * so those two steps live here.
 */
import { clampTooltipToViewport } from '../core/tooltipPlacement.js';
import { t } from '../../../../strings/index.js';

const CRITICAL_COLOR = 'var(--color-sev-critical-text)';
const MAJOR_COLOR = 'var(--color-sev-major-text)';
const MINOR_COLOR = 'var(--color-sev-minor-text)';

/**
 * Append one row per non-zero severity count, worst first.
 *
 * @param {string[]} rows Row HTML accumulated so far; appended to in place.
 * @param {(label: string, value: *, color: string) => string} row The caller's row renderer.
 * @param {number|null|undefined} critical
 * @param {number|null|undefined} major
 * @param {number|null|undefined} minor
 */
export function pushSeverityRows(rows, row, critical, major, minor) {
  if (critical) rows.push(row(t('map.critical'), critical, CRITICAL_COLOR));
  if (major) rows.push(row(t('map.major'), major, MAJOR_COLOR));
  if (minor) rows.push(row(t('map.minor'), minor, MINOR_COLOR));
}

/**
 * Show the tooltip with `html`, positioned at the pointer and clamped so it
 * stays inside the viewport.
 *
 * @param {HTMLElement} el The tooltip element.
 * @param {string} html Markup to display.
 * @param {number} cx Client X of the pointer.
 * @param {number} cy Client Y of the pointer.
 */
export function showTooltip(el, html, cx, cy) {
  el.innerHTML = html;
  el.style.display = 'block';
  const { left, top } = clampTooltipToViewport(cx, cy, window.innerWidth, window.innerHeight);
  el.style.left = left + 'px';
  el.style.top = top + 'px';
}
