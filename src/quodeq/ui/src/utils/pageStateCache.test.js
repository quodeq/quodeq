import test from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_SCOPES_PER_NAMESPACE, clearAllCachedState, readCachedState, writeCachedState,
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
