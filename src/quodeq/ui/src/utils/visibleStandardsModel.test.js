import test from 'node:test';
import assert from 'node:assert/strict';
import { decideHydration, sameIdSet } from './visibleStandardsModel.js';

// ---------------------------------------------------------------------------
// sameIdSet
// ---------------------------------------------------------------------------

test('sameIdSet: true for set-equal arrays regardless of order/duplicates', () => {
  assert.equal(sameIdSet(['a', 'b'], ['b', 'a']), true);
  assert.equal(sameIdSet([], []), true);
});

test('sameIdSet: false when sizes or members differ, or either input is not an array', () => {
  assert.equal(sameIdSet(['a'], ['a', 'b']), false);
  assert.equal(sameIdSet(['a'], ['b']), false);
  assert.equal(sameIdSet(null, ['a']), false);
  assert.equal(sameIdSet(['a'], null), false);
});

// ---------------------------------------------------------------------------
// decideHydration
// ---------------------------------------------------------------------------

const DEFAULTS = ['security', 'reliability'];

test('decideHydration: migrate when isDefault, not yet migrated, and the cache differs from the ISO defaults', () => {
  const decision = decideHydration({
    serverIds: DEFAULTS, isDefault: true, serverDefaults: undefined,
    cachedIds: ['security'], alreadyMigrated: false, fallbackDefaults: DEFAULTS,
  });
  assert.deepEqual(decision, { kind: 'migrate', ids: ['security'] });
});

test('decideHydration: adopt (no migrate) when the cache already equals the ISO defaults', () => {
  const decision = decideHydration({
    serverIds: DEFAULTS, isDefault: true, serverDefaults: undefined,
    cachedIds: [...DEFAULTS].reverse(), alreadyMigrated: false, fallbackDefaults: DEFAULTS,
  });
  assert.deepEqual(decision, { kind: 'adopt', ids: DEFAULTS, markMigrated: false });
});

test('decideHydration: adopt (no migrate) when there is no cached selection', () => {
  const decision = decideHydration({
    serverIds: DEFAULTS, isDefault: true, serverDefaults: undefined,
    cachedIds: null, alreadyMigrated: false, fallbackDefaults: DEFAULTS,
  });
  assert.deepEqual(decision, { kind: 'adopt', ids: DEFAULTS, markMigrated: false });
});

test('decideHydration: adopt (no migrate) when migration already happened once for this browser', () => {
  const decision = decideHydration({
    serverIds: DEFAULTS, isDefault: true, serverDefaults: undefined,
    cachedIds: ['security'], alreadyMigrated: true, fallbackDefaults: DEFAULTS,
  });
  assert.deepEqual(decision, { kind: 'adopt', ids: DEFAULTS, markMigrated: false });
});

test('decideHydration: adopt and markMigrated when the server already has its own real file', () => {
  const decision = decideHydration({
    serverIds: ['reliability'], isDefault: false, serverDefaults: undefined,
    cachedIds: ['security'], alreadyMigrated: false, fallbackDefaults: DEFAULTS,
  });
  assert.deepEqual(decision, { kind: 'adopt', ids: ['reliability'], markMigrated: true });
});

test('decideHydration: prefers the server-provided defaults over the fallback constant for the migration comparison', () => {
  const serverDefaults = ['security', 'reliability'];
  // Cache matches the server's defaults but NOT the (different) fallback constant.
  const decision = decideHydration({
    serverIds: serverDefaults, isDefault: true, serverDefaults,
    cachedIds: [...serverDefaults], alreadyMigrated: false, fallbackDefaults: ['maintainability'],
  });
  assert.equal(decision.kind, 'adopt');
});
