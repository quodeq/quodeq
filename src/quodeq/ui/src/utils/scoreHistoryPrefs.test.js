import test from 'node:test';
import assert from 'node:assert/strict';
import { readScoreHistoryGranularity, writeScoreHistoryGranularity } from './scoreHistoryPrefs.js';

function fakeStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, String(v)); },
    removeItem: (k) => { map.delete(k); },
  };
}

test('read: returns "day" when nothing stored', () => {
  assert.equal(readScoreHistoryGranularity(fakeStorage()), 'day');
});

test('read: returns a valid stored value', () => {
  assert.equal(readScoreHistoryGranularity(fakeStorage({ 'quodeq-score-history-granularity': 'month' })), 'month');
});

test('read: falls back to "day" on an invalid stored value', () => {
  assert.equal(readScoreHistoryGranularity(fakeStorage({ 'quodeq-score-history-granularity': 'decade' })), 'day');
});

test('write then read round-trips a valid value', () => {
  const s = fakeStorage();
  writeScoreHistoryGranularity('week', s);
  assert.equal(readScoreHistoryGranularity(s), 'week');
});

test('write: ignores an invalid value (does not persist garbage)', () => {
  const s = fakeStorage({ 'quodeq-score-history-granularity': 'week' });
  writeScoreHistoryGranularity('decade', s);
  assert.equal(readScoreHistoryGranularity(s), 'week');
});
