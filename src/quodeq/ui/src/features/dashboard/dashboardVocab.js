import { FINDING_TYPE } from '../../vocab/findingType.js';

// The global publish job's state machine, mirrored by the backend's own
// publish/status payload (services/shared_publish.py's PublishState; the
// parity test is tests/tools/test_vocab_mirrors_match_ui.py).
export const PUBLISH_STATE = Object.freeze({
  IDLE: 'idle', RUNNING: 'running', DONE: 'done', ERROR: 'error',
});

// The overview hero's clickable stat cards: 'violations' is its own kind
// (heroCardHandlers emits it as a whole-file-set filter, not a finding
// type); COMPLIANCE reuses FINDING_TYPE.COMPLIANCE since it is the same
// value read back by the explorer's severityFilter comparisons. A severity
// level (critical/major/minor) passes through unchanged as its own kind.
export const HERO_CARD_KIND = Object.freeze({ VIOLATIONS: 'violations', COMPLIANCE: FINDING_TYPE.COMPLIANCE });

// deriveAction's verdict for a merged local/shared project entry
// (projectsMerge.js): what the card's action button should offer. null
// means no action needed.
export const PROJECT_ACTION = Object.freeze({ PUBLISH: 'publish', UPDATE: 'update', PULL: 'pull' });
