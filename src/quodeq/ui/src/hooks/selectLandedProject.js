import { NAV_TAB } from '../vocab/navTab.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';

/**
 * Whether a project that just landed (an add, or a clone that finished)
 * should become the selected one. Yes on the Repositories tab, where the
 * add happened and the card lights up, and when nothing is selected yet (a
 * first project). No while the user looks at another project's pages: a
 * selection change would swap the screen under them.
 * @param {{ activeTab?: string, selectedProject?: string|null }} state
 * @returns {boolean}
 */
export function shouldSelectLanded(state) {
  return state.activeTab === NAV_TAB.PROJECTS || !state.selectedProject;
}

/**
 * Select the landed local project when shouldSelectLanded says so. A null
 * id (a clone still running) is a no-op.
 * @param {{ activeTab?: string, selectedProject?: string|null, handleProjectChange?: Function }} state
 * @param {string|null|undefined} projectId
 */
export function selectLandedProject(state, projectId) {
  if (!projectId || !shouldSelectLanded(state)) return;
  state.handleProjectChange?.(projectId, PROJECT_SOURCE.LOCAL);
}
