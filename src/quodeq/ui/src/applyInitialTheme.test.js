import test from 'node:test';
import assert from 'node:assert/strict';
import { applyInitialTheme } from './applyInitialTheme.js';

function storageOf(map) {
  return {
    getItem: (k) => (k in map ? map[k] : null),
    setItem: (k, v) => { map[k] = v; },
    removeItem: (k) => { delete map[k]; },
  };
}

// main.jsx calls applyInitialTheme() at boot with no try/catch upstream of
// this function; it must throw (not swallow) so main.jsx's boundary catch
// is what decides what happens on failure, not this function.
test('applyInitialTheme: a storage failure propagates to the caller', () => {
  const boom = new Error('storage blocked');
  const storage = { getItem: () => { throw boom; } };
  assert.throws(() => applyInitialTheme(storage, () => ({ matches: false })), boom);
});

test('applyInitialTheme: the default system/daruma combination never touches the DOM', () => {
  // No `document` global exists in this plain-Node test file. If
  // applyInitialTheme reached document.documentElement it would throw
  // ReferenceError, so this also proves the null-dataTheme branch is
  // taken for the default system/daruma combination.
  const storage = storageOf({});
  assert.doesNotThrow(() => applyInitialTheme(storage, () => ({ matches: false })));
});

test('applyInitialTheme: a non-daruma family sets the data-theme attribute', () => {
  const storage = storageOf({ 'cc-theme-mode': 'dark', 'cc-theme-family': 'ifrit' });
  let applied = null;
  global.document = { documentElement: { setAttribute: (name, value) => { applied = [name, value]; } } };
  try {
    applyInitialTheme(storage, () => ({ matches: false }));
    assert.deepEqual(applied, ['data-theme', 'ifrit-dark']);
  } finally {
    delete global.document;
  }
});
