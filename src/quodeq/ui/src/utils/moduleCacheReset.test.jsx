import { expect, test } from 'vitest';

import {
  clearAllCachedState, readCachedState, resetCachedScope, writeCachedState,
} from './pageStateCache.js';
import { resetWriteGeneration, writeVisibleStandardIds } from './visibleStandards.js';

/** Thin asserts so the body reads like the node:test siblings. */
const expect_deep = (actual, expected) => expect(actual).toEqual(expected);
const expect_eq = (actual, expected) => expect(actual).toBe(expected);

const fakeStorage = () => ({
  data: {},
  getItem(k) { return k in this.data ? this.data[k] : null; },
  setItem(k, v) { this.data[k] = String(v); },
  removeItem(k) { delete this.data[k]; },
});

test('pageStateCache: clearAllCachedState empties every namespace', () => {
  writeCachedState('map', 'proj-1', { tab: 'files' });
  writeCachedState('violations', 'proj-1', { filter: 'major' });
  expect_deep(readCachedState('map', 'proj-1', {}), { tab: 'files' });

  clearAllCachedState();

  expect_deep(readCachedState('map', 'proj-1', { tab: 'default' }), { tab: 'default' });
  expect_deep(readCachedState('violations', 'proj-1', {}), {});
});

test('pageStateCache: clearing all is broader than resetting one scope', () => {
  writeCachedState('map', 'proj-1', { tab: 'files' });
  writeCachedState('map', 'proj-2', { tab: 'folders' });

  resetCachedScope('map', 'proj-1');
  expect_deep(readCachedState('map', 'proj-2', {}), { tab: 'folders' });

  clearAllCachedState();
  expect_deep(readCachedState('map', 'proj-2', {}), {});
});

test('visibleStandards: the write generation is resettable', () => {
  const s = fakeStorage();
  writeVisibleStandardIds(['a'], s);
  writeVisibleStandardIds(['b'], s);

  // The module's own note asks for this hook: without it, a promise left
  // dangling across a test boundary trips the next caller's staleness check.
  expect_eq(resetWriteGeneration(), 0);
  expect_deep(JSON.parse(s.data['quodeq-visible-standards']), ['b']);
});
