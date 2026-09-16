// Wizard step ids: the `step` state value, goToStep's argument and the
// startStep an entry point opens on. STEP_ORDER is the forward path.
// SKIPPED_KEY is the localStorage flag set when the user dismisses the
// welcome step ("Maybe later").
//
// Leaf module by design (no imports): routes/navigationBundle.js,
// useWizardLifecycle.js, EmptyStateWithTour.jsx and useWizardState.js are in
// the entry chunk and read these ids; importing them from the handlers hook
// or the draft-persistence module would pull the lazy wizard in with them.
export const STEP_WELCOME = 'welcome';
export const STEP_REPO_SCAN = 'repo-scan';
export const STEP_PROVIDER = 'provider';
export const STEP_STANDARD_LAUNCH = 'standard-launch';
export const STEP_ORDER = [STEP_WELCOME, STEP_REPO_SCAN, STEP_PROVIDER, STEP_STANDARD_LAUNCH];

export const SKIPPED_KEY = 'quodeq_onboarding_skipped';
