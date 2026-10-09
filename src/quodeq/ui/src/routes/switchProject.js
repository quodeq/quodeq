import { NAV_TAB } from '../vocab/navTab.js';

/**
 * Make `id` the active project, the one selection path shared by a
 * Repositories card click and the topbar project switcher.
 *
 * Where you land depends on where you picked it from: from Repositories you
 * go to the new project's Overview; from a project-scoped page you stay on
 * that page, reset to its tab root when you were in a drill-down (a file or
 * finding of the old project means nothing for the new one).
 *
 * @param {{ handleProjectChange: Function, navTab: Function }} navigation
 * @param {string} id
 * @param {string} [source] - PROJECT_SOURCE value; the selection default when omitted
 * @param {{ rootTab?: string, depth?: number }} [where] - the nav stack's root page and depth
 */
export function switchProject(navigation, id, source, { rootTab = NAV_TAB.PROJECTS, depth = 1 } = {}) {
  navigation.handleProjectChange(id, source);
  if (rootTab === NAV_TAB.PROJECTS) navigation.navTab(NAV_TAB.OVERVIEW);
  else if (depth > 1) navigation.navTab(rootTab);
}
