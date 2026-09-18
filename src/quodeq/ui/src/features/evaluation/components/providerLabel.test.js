import test from 'node:test';
import assert from 'node:assert/strict';
import { readActiveProviderModel } from './providerLabel.js';

// readActiveProviderModel used to call storage.getItem directly with no
// guard, bypassing the adapter that handles private-mode/blocked storage.
// A throwing storage must degrade to "no active provider" instead of
// propagating.
test('readActiveProviderModel returns null instead of throwing when storage access is blocked', () => {
  const throwing = {
    getItem() { throw new Error('blocked'); },
    setItem() {},
  };
  assert.equal(readActiveProviderModel(throwing), null);
});

test('readActiveProviderModel reads provider and model from storage', () => {
  const store = new Map([
    ['cc-active-provider', 'openai'],
    ['cc-openai-model', 'gpt-5'],
  ]);
  const storage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
  };
  assert.deepEqual(readActiveProviderModel(storage), { provider: 'openai', model: 'gpt-5' });
});

test('readActiveProviderModel returns null when no provider is active', () => {
  const storage = { getItem: () => null, setItem() {} };
  assert.equal(readActiveProviderModel(storage), null);
});
