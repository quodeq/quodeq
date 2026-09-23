// The wizard's repo-scan sub-step states (`repoScanSubState`): written by
// hooks/useWizardState.js, read by RepoScanStep.jsx and the wizard handlers.
// Its own vocabulary, not the run/job/dim one in src/vocab.
export const SCAN_SUB_STATE = Object.freeze({ IDLE: 'idle', SCANNING: 'scanning', SCANNED: 'scanned', ERROR: 'error' });
