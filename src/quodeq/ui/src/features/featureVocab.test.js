// Feature vocabularies each live in one small module that the writing hook
// and its readers both import, instead of the readers importing the hook.
// LOG_STREAM_STATUS lives in vocab/logStreamStatus.js (shared by two
// features) and is pinned in vocab/vocab.test.js instead.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { SCAN_SUB_STATE } from './onboarding/onboardingVocab.js';
import { PUBLISH_STATE } from './dashboard/dashboardVocab.js';

test('feature vocab modules spell their values and are frozen', () => {
  assert.deepEqual(SCAN_SUB_STATE, { IDLE: 'idle', SCANNING: 'scanning', SCANNED: 'scanned', ERROR: 'error' });
  assert.deepEqual(PUBLISH_STATE, { IDLE: 'idle', RUNNING: 'running', DONE: 'done', ERROR: 'error' });
  for (const obj of [SCAN_SUB_STATE, PUBLISH_STATE]) assert.equal(Object.isFrozen(obj), true);
});
