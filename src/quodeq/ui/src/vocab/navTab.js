// Nav-stack page ids: the sidebar/topbar's top-level tabs (hooks/useAppState.js's
// KNOWN_TABS) plus the deeper drill-down page ids the routes push. No Python
// mirror: a purely client-side routing concept, but one value per concept so
// 'overview' (say) means the same thing everywhere it's compared.
export const NAV_TAB = Object.freeze({
  OVERVIEW: 'overview',
  VIOLATIONS: 'violations',
  MAP: 'map',
  HISTORY: 'history',
  PROJECTS: 'projects',
  EVALUATE: 'evaluate',
  STANDARDS: 'standards',
  HELP: 'help',
  SETTINGS: 'settings',
  COMPARE: 'compare',
  // Drill-down pages, not top-level tabs (not part of KNOWN_TABS).
  HISTORY_RUN: 'history-run',
  RUN: 'run',
  EXPLORER: 'explorer',
  EVAL_PRINCIPLE: 'evalprinciple',
  // Legacy id predating the EVAL_PRINCIPLE rename, still reachable via saved
  // links/history.
  EVAL_PRINCIPLE_DETAIL: 'eval-principle-detail',
});
