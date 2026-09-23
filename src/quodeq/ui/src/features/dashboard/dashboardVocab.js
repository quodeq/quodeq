// The global publish job's state machine, mirrored by the backend's own
// publish/status payload (services/shared_publish.py's PublishState; the
// parity test is tests/tools/test_vocab_mirrors_match_ui.py).
export const PUBLISH_STATE = Object.freeze({
  IDLE: 'idle', RUNNING: 'running', DONE: 'done', ERROR: 'error',
});
