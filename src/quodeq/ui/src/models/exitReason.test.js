import test from 'node:test';
import assert from 'node:assert/strict';
import { exitReasonInfo, exitReasonLabel, exitReasonHint, exitReasonWarn } from './exitReason.js';

test('provider_fatal maps to a label and an actionable hint', () => {
  const info = exitReasonInfo('provider_fatal');
  assert.equal(info.label, 'AI provider error');
  assert.match(info.hint, /quota|credits|API key/);
});

test('failure_streak and agent_failure_streak share the same guidance', () => {
  assert.deepEqual(exitReasonInfo('agent_failure_streak'), exitReasonInfo('failure_streak'));
  assert.match(exitReasonHint('failure_streak'), /running and reachable/);
});

test('deadline and time_limit share the same guidance', () => {
  assert.deepEqual(exitReasonInfo('deadline'), exitReasonInfo('time_limit'));
  assert.equal(exitReasonLabel('deadline'), 'time limit reached');
});

test('cancelled has a label but no hint', () => {
  assert.equal(exitReasonLabel('cancelled_signal'), 'cancelled');
  assert.equal(exitReasonHint('cancelled'), null);
});

test('unknown codes pass through verbatim with no hint', () => {
  assert.equal(exitReasonInfo('some_future_code'), null);
  assert.equal(exitReasonLabel('some_future_code'), 'some_future_code');
  assert.equal(exitReasonHint('some_future_code'), null);
});

test('provider failures warn on done runs, clean stops do not', () => {
  assert.equal(exitReasonWarn('provider_fatal'), true);
  assert.equal(exitReasonWarn('failure_streak'), true);
  assert.equal(exitReasonWarn('agent_failure_streak'), true);
  assert.equal(exitReasonWarn('time_limit'), false);
  assert.equal(exitReasonWarn('cancelled'), false);
  assert.equal(exitReasonWarn('unknown_code'), false);
  assert.equal(exitReasonWarn(null), false);
});

test('absent codes yield null label and hint', () => {
  assert.equal(exitReasonInfo(null), null);
  assert.equal(exitReasonLabel(undefined), undefined);
  assert.equal(exitReasonHint(null), null);
});
