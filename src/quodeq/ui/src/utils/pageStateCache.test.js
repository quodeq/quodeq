import test from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_SCOPES_PER_NAMESPACE, clearAllCachedState, readCachedState, writeCachedState,
  createPageStateCache, defaultPageStateCache,
} from './pageStateCache.js';

function fill(namespace, count) {
  for (let i = 0; i < count; i++) writeCachedState(namespace, `proj-${i}`, { tab: i });
}

test('pageStateCache: evicts the least recently used scope once a namespace exceeds the cap', () => {
  clearAllCachedState();
  fill('map', MAX_SCOPES_PER_NAMESPACE);
  // Reading refreshes recency, so proj-0 survives and proj-1 is now oldest.
  assert.deepEqual(readCachedState('map', 'proj-0', {}), { tab: 0 });

  writeCachedState('map', 'proj-extra', { tab: 'x' });

  assert.deepEqual(readCachedState('map', 'proj-1', { tab: 'default' }), { tab: 'default' });
  assert.deepEqual(readCachedState('map', 'proj-0', {}), { tab: 0 });
  assert.deepEqual(readCachedState('map', 'proj-extra', {}), { tab: 'x' });
});

test('pageStateCache: the cap applies per namespace', () => {
  clearAllCachedState();
  fill('map', MAX_SCOPES_PER_NAMESPACE);
  writeCachedState('violations', 'proj-v', { fileCurrentPath: 'src' });

  assert.deepEqual(readCachedState('map', 'proj-0', {}), { tab: 0 });
  assert.deepEqual(readCachedState('violations', 'proj-v', {}), { fileCurrentPath: 'src' });
});

test('pageStateCache: a patch merges into the scope and defaults fill the gaps', () => {
  clearAllCachedState();
  writeCachedState('map', 'proj-1', { a: 1 });
  writeCachedState('map', 'proj-1', { b: 2 });
  assert.deepEqual(readCachedState('map', 'proj-1', { c: 3 }), { a: 1, b: 2, c: 3 });
});

test('createPageStateCache: two instances never share scopes', () => {
  const a = createPageStateCache();
  const b = createPageStateCache();
  a.writeCachedState('map', 'proj-1', { tab: 'files' });
  assert.deepEqual(a.readCachedState('map', 'proj-1', {}), { tab: 'files' });
  assert.deepEqual(b.readCachedState('map', 'proj-1', {}), {});
});

test('createPageStateCache: maxScopes is injectable independent of MAX_SCOPES_PER_NAMESPACE', () => {
  const cache = createPageStateCache({ maxScopes: 2 });
  cache.writeCachedState('map', 'proj-0', { tab: 0 });
  cache.writeCachedState('map', 'proj-1', { tab: 1 });
  cache.writeCachedState('map', 'proj-2', { tab: 2 }); // evicts proj-0, the LRU
  assert.deepEqual(cache.readCachedState('map', 'proj-0', { tab: 'default' }), { tab: 'default' });
  assert.deepEqual(cache.readCachedState('map', 'proj-2', {}), { tab: 2 });
});

test('pageStateCache: the module-level exports delegate to defaultPageStateCache, not a private store', () => {
  clearAllCachedState();
  defaultPageStateCache.writeCachedState('map', 'proj-1', { tab: 'files' });
  // Written straight through defaultPageStateCache is visible via the free
  // module functions, and vice versa -- proving they share one store.
  assert.deepEqual(readCachedState('map', 'proj-1', {}), { tab: 'files' });
  writeCachedState('map', 'proj-2', { tab: 'folders' });
  assert.deepEqual(defaultPageStateCache.readCachedState('map', 'proj-2', {}), { tab: 'folders' });
  clearAllCachedState();
});
