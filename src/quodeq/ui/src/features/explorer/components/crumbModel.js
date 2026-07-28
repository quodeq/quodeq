/**
 * Pure model for the topbar address: decides which crumbs stay visible and
 * which collapse behind the "…" chip (Finder-style collapse-the-middle).
 *
 * Rules, in order:
 *   - the first crumb (project root) and the last crumb (current page) are
 *     always visible;
 *   - run-date segments ("history / 28 jul 2026") never render as visible
 *     intermediates — the run date belongs under the page title, not in the
 *     address — but they stay reachable through the "…" ancestor menu;
 *   - when the path is deeper than `maxVisible` crumbs, everything between
 *     the root and the last two segments collapses.
 */

const RUN_DATE_PAGES = new Set(['run', 'history-run']);

export function isRunDateEntry(entry) {
  return RUN_DATE_PAGES.has(entry?.page);
}

/**
 * @param {Array<{label: string, index: number, isProject?: boolean, isRunDate?: boolean}>} crumbs
 * @param {{maxVisible?: number}} [opts]
 * @returns {Array} display items in order: the visible crumbs, with a single
 *   `{ellipsis: true, hidden: [...crumbs]}` marker at the position of the
 *   first collapsed crumb. `hidden` preserves path order.
 */
export function collapseCrumbs(crumbs, { maxVisible = 4 } = {}) {
  if (crumbs.length <= 1) return crumbs.slice();
  const last = crumbs.length - 1;
  const hidden = new Set();
  if (crumbs.length > maxVisible) {
    for (let i = 1; i <= last - 2; i++) hidden.add(i);
  }
  for (let i = 1; i < last; i++) {
    if (crumbs[i].isRunDate) hidden.add(i);
  }
  if (hidden.size === 0) return crumbs.slice();

  const out = [];
  let marker = null;
  for (let i = 0; i < crumbs.length; i++) {
    if (hidden.has(i)) {
      if (!marker) {
        marker = { ellipsis: true, hidden: [] };
        out.push(marker);
      }
      marker.hidden.push(crumbs[i]);
    } else {
      out.push(crumbs[i]);
    }
  }
  return out;
}
