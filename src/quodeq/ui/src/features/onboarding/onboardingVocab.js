// The wizard's repo-scan sub-step states (`repoScanSubState`): written by
// hooks/useWizardState.js, read by RepoScanStep.jsx and the wizard handlers.
// Its own vocabulary, not the run/job/dim one in src/vocab.
export const SCAN_SUB_STATE = Object.freeze({ IDLE: 'idle', SCANNING: 'scanning', SCANNED: 'scanned', ERROR: 'error' });

// Where the wizard was opened from, carried on the wizard entry as `source`:
// the lifecycle's auto-open (FIRST_RUN), "add a project" and "take the tour"
// (ADD), Settings' "show welcome" (SETTINGS), and the Repositories page's
// "connect" (CONNECT). The welcome adapts to it: from Settings it offers no
// "skip for now" and never writes the skip flag. Leaf module (no imports),
// so the entry-chunk navigation bundle can read it without pulling the lazy
// wizard in.
export const WIZARD_SOURCE = Object.freeze({
  FIRST_RUN: 'first-run',
  ADD: 'add',
  SETTINGS: 'settings',
  CONNECT: 'connect',
});

// Where a repository comes from in the url-or-folder forms (the connect
// step's evaluations repository, and the wizard state's `repo.source`): a
// pasted git url, or a local folder picked in the folder browser.
export const REPO_SOURCE = Object.freeze({ URL: 'url', FOLDER: 'folder' });

// A local folder travels to the API as a file url: this prefix plus the
// absolute path (the server rejects relative paths and dot segments).
export const FILE_URL_PREFIX = 'file://';
