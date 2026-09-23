// The vocab modules mirror the Python StrEnums. These assertions are the
// mirror: a value drifting from src/quodeq/core/**'s wire spelling breaks here.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { RUN_STATE, TERMINAL_RUN_STATES } from './runState.js';
import { EXTERNAL_JOB_PREFIX, JOB_STATUS, JOB_TERMINAL, JOB_FINISHED, isExternalJobId } from './jobStatus.js';
import { EXIT_REASON } from './exitReason.js';
import { SEVERITY, SEVERITY_ORDER } from './severity.js';
import { GRADE, GRADE_LADDER } from './grade.js';
import { DIM_STATE } from './dimState.js';
import { FINDING_TYPE } from './findingType.js';
import { PROJECT_SOURCE, DEFAULT_PROJECT_SOURCE } from './projectSource.js';

test('vocab modules spell the wire values', () => {
  assert.deepEqual(RUN_STATE, {
    PENDING: 'pending', RUNNING: 'running', FINALIZING: 'finalizing',
    DONE: 'done', FAILED: 'failed', CANCELLED: 'cancelled',
  });
  assert.deepEqual([...TERMINAL_RUN_STATES], ['done', 'failed', 'cancelled']);
  assert.deepEqual(JOB_STATUS, {
    RUNNING: 'running', DONE: 'done', FAILED: 'failed', CANCELLED: 'cancelled', LOST: 'lost',
  });
  assert.deepEqual([...JOB_TERMINAL], ['done', 'failed', 'cancelled', 'lost']);
  assert.deepEqual([...JOB_FINISHED], ['done', 'failed', 'cancelled']);
  assert.deepEqual(Object.values(EXIT_REASON), [
    'done', 'time_limit', 'deadline', 'failure_streak', 'cancelled', 'error',
    'stale_detected', 'stale_legacy_pid_dead', 'stale_legacy_no_pid',
  ]);
  assert.deepEqual(SEVERITY, { CRITICAL: 'critical', MAJOR: 'major', MINOR: 'minor' });
  assert.deepEqual(SEVERITY_ORDER, ['critical', 'major', 'minor']);
  assert.deepEqual(GRADE, {
    EXEMPLARY: 'Exemplary', GOOD: 'Good', ADEQUATE: 'Adequate', POOR: 'Poor', INSUFFICIENT: 'Insufficient',
  });
  assert.deepEqual(GRADE_LADDER, Object.values(GRADE));
  assert.deepEqual(DIM_STATE, {
    PENDING: 'pending', RUNNING: 'running', DONE: 'done', INCOMPLETE: 'incomplete',
  });
  assert.deepEqual(FINDING_TYPE, { VIOLATION: 'violation', COMPLIANCE: 'compliance' });
  assert.deepEqual(PROJECT_SOURCE, { LOCAL: 'local', SHARED: 'shared' });
  assert.equal(DEFAULT_PROJECT_SOURCE, 'local');
});

test('vocab modules are frozen', () => {
  for (const obj of [RUN_STATE, JOB_STATUS, EXIT_REASON, SEVERITY, GRADE, DIM_STATE, FINDING_TYPE, PROJECT_SOURCE]) {
    assert.equal(Object.isFrozen(obj), true);
  }
});

test('external job ids carry the ext- prefix', () => {
  assert.equal(EXTERNAL_JOB_PREFIX, 'ext-');
  assert.equal(isExternalJobId('ext-abc'), true);
  assert.equal(isExternalJobId('abc'), false);
});
