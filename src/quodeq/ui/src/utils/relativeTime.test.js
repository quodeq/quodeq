import test from 'node:test';
import assert from 'node:assert/strict';
import { relativeTime, relativeTimeFine } from './relativeTime.js';
import { MS_PER_DAY } from './time.js';

const MINUTE = 60000;

test('relativeTime accepts epoch ms as well as an ISO string', () => {
  const then = Date.now() - 3 * MS_PER_DAY;
  assert.equal(relativeTime(then), '3 days ago');
  assert.equal(relativeTime(new Date(then).toISOString()), '3 days ago');
});

test('relativeTime is null for a missing or invalid timestamp', () => {
  assert.equal(relativeTime(null), null);
  assert.equal(relativeTime(undefined), null);
  assert.equal(relativeTime('not-a-date'), null);
});

test('relativeTimeFine reads "just now" under a minute', () => {
  assert.equal(relativeTimeFine(Date.now() - 10000), 'just now');
});

test('relativeTimeFine reads minutes under an hour and hours under a day', () => {
  assert.equal(relativeTimeFine(Date.now() - 2 * MINUTE), '2 min ago');
  assert.equal(relativeTimeFine(Date.now() - 3 * 60 * MINUTE), '3 h ago');
});

test('relativeTimeFine falls back to the day-granular wording from a day on', () => {
  assert.equal(relativeTimeFine(Date.now() - 2 * MS_PER_DAY), '2 days ago');
});

test('relativeTimeFine is null for a missing timestamp', () => {
  assert.equal(relativeTimeFine(null), null);
});
