// The global publish job's state machine, mirrored by the backend's own
// publish/status payload (services/shared_publish.py's PublishState; the
// parity test is tests/tools/test_vocab_mirrors_match_ui.py).
export const PUBLISH_STATE = Object.freeze({
  IDLE: 'idle', RUNNING: 'running', DONE: 'done', ERROR: 'error',
});

// The overview hero's clickable stat cards: 'violations' and 'compliance'
// are the two fixed kinds heroCardHandlers emits; a severity level
// (critical/major/minor) passes through unchanged as its own kind. The
// overview panels' card-navigate builders read these back to decide the
// file view's severityFilter.
export const HERO_CARD_KIND = Object.freeze({ VIOLATIONS: 'violations', COMPLIANCE: 'compliance' });

// deriveAction's verdict for a merged local/shared project entry
// (projectsMerge.js): what the card's action button should offer. null
// means no action needed.
export const PROJECT_ACTION = Object.freeze({ PUBLISH: 'publish', UPDATE: 'update', PULL: 'pull' });
