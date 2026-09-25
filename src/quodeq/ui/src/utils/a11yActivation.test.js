import test from 'node:test';
import assert from 'node:assert/strict';
import { activationHandlers } from './a11y.js';

test('activationHandlers runs the action on click', () => {
  const calls = [];
  activationHandlers(() => calls.push('run')).onClick({});
  assert.deepEqual(calls, ['run']);
});

test('activationHandlers runs the action on Enter and Space only, preventing their default', () => {
  const calls = [];
  const { onKeyDown } = activationHandlers(() => calls.push('run'));
  for (const key of ['Enter', ' ', 'a']) onKeyDown({ key, preventDefault: () => calls.push(`prevent:${key}`) });
  assert.deepEqual(calls, ['prevent:Enter', 'run', 'prevent: ', 'run']);
});
