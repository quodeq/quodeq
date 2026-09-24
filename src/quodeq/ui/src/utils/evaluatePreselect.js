import { NAV_TAB } from '../vocab/navTab.js';

/**
 * Maps the active nav-stack entry to the standard ids the evaluate screen
 * should preselect. Returns [] for any page that carries no standard context
 * (overview, violations, map, history, a plain sidebar/topbar launch).
 *
 * @param {{ page?: string, dimension?: string, evalPrincipal?: { dimension?: string } } | null | undefined} activePage
 * @returns {string[]}
 */
export function deriveEvaluatePreselect(activePage) {
  if (!activePage) return [];
  const { page } = activePage;
  if (page === NAV_TAB.EXPLORER && activePage.dimension) {
    return [activePage.dimension];
  }
  if (
    (page === NAV_TAB.EVAL_PRINCIPLE || page === NAV_TAB.EVAL_PRINCIPLE_DETAIL) &&
    activePage.evalPrincipal?.dimension
  ) {
    return [activePage.evalPrincipal.dimension];
  }
  return [];
}
