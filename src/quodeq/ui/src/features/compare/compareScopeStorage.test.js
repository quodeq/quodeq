import test from 'node:test';
import assert from 'node:assert/strict';
import { readStoredScope, storeScope, SCOPE_STORAGE_KEY } from './compareScopeStorage.js';

function fakeStorage(entries = {}) {
  const store = { ...entries };
  return {
    getItem: (key) => (key in store ? store[key] : null),
    setItem: (key, value) => { store[key] = String(value); },
    removeItem: (key) => { delete store[key]; },
    _store: store,
  };
}

test('readStoredScope returns null when nothing is stored', () => {
  assert.equal(readStoredScope(fakeStorage()), null);
});

test('readStoredScope returns the stored array', () => {
  const s = fakeStorage({ [SCOPE_STORAGE_KEY]: JSON.stringify(['alpha', 'beta']) });
  assert.deepEqual(readStoredScope(s), ['alpha', 'beta']);
});

test('readStoredScope guards against a non-array payload', () => {
  const s = fakeStorage({ [SCOPE_STORAGE_KEY]: JSON.stringify({ not: 'an array' }) });
  assert.equal(readStoredScope(s), null);
});

test('readStoredScope returns null on malformed JSON', () => {
  const s = fakeStorage({ [SCOPE_STORAGE_KEY]: 'not json' });
  assert.equal(readStoredScope(s), null);
});

test('storeScope(null) removes the key', () => {
  const s = fakeStorage({ [SCOPE_STORAGE_KEY]: JSON.stringify(['alpha']) });
  storeScope(null, s);
  assert.equal(SCOPE_STORAGE_KEY in s._store, false);
});

test('storeScope(ids) writes the JSON-serialized array', () => {
  const s = fakeStorage();
  storeScope(['alpha', 'beta'], s);
  assert.deepEqual(JSON.parse(s._store[SCOPE_STORAGE_KEY]), ['alpha', 'beta']);
});
