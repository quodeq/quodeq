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
  if (page === 'explorer' && activePage.dimension) {
    return [activePage.dimension];
  }
  if (
    (page === 'evalprinciple' || page === 'eval-principle-detail') &&
    activePage.evalPrincipal?.dimension
  ) {
    return [activePage.evalPrincipal.dimension];
  }
  return [];
}
