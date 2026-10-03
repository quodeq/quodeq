// Lifecycle of the grade-formula editor's worked example (useStageExplain):
// the stored stages load once, then each draft change recomputes them. No
// Python mirror: the state is UI-only, so this lives in vocab/ as a UI-only
// exception (see tests/tools/test_vocab_mirrors_match_ui.py).
export const STAGE_STATUS = Object.freeze({
  IDLE: 'idle', LOADING: 'loading', READY: 'ready', UNAVAILABLE: 'unavailable', ERROR: 'error',
});
