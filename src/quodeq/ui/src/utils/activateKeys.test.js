import { test } from 'node:test';
import assert from 'node:assert/strict';
import { onActivateKeys } from './activateKeys.js';

function keydown(key, { nested = false } = {}) {
  const el = {};
  let prevented = false;
  return { e: { key, currentTarget: el, target: nested ? {} : el, preventDefault: () => { prevented = true; } }, prevented: () => prevented };
}

test('Enter and Space activate and prevent the default', () => {
  for (const key of ['Enter', ' ']) {
    let calls = 0;
    const k = keydown(key);
    onActivateKeys(() => { calls += 1; })(k.e);
    assert.equal(calls, 1);
    assert.equal(k.prevented(), true);
  }
});

test('other keys and keys from a nested control are left alone', () => {
  let calls = 0;
  const handler = onActivateKeys(() => { calls += 1; });
  handler(keydown('a').e);
  handler(keydown('Enter', { nested: true }).e);
  assert.equal(calls, 0);
});
