// Nav-stack page ids that carry standard context. 'eval-principle-detail' is
// a legacy id predating the 'evalprinciple' rename, still reachable via saved
// links/history.
const PAGE_EXPLORER = 'explorer';
const PAGE_EVAL_PRINCIPLE = 'evalprinciple';
const PAGE_EVAL_PRINCIPLE_DETAIL = 'eval-principle-detail';

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
  if (page === PAGE_EXPLORER && activePage.dimension) {
    return [activePage.dimension];
  }
  if (
    (page === PAGE_EVAL_PRINCIPLE || page === PAGE_EVAL_PRINCIPLE_DETAIL) &&
    activePage.evalPrincipal?.dimension
  ) {
    return [activePage.evalPrincipal.dimension];
  }
  return [];
}
