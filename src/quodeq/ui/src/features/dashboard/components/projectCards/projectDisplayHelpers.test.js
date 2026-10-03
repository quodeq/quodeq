import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatDate } from './projectDisplayHelpers.js';

test('formatDate: an invalid iso string returns null, not "Invalid Date"', () => {
  assert.equal(formatDate('not-a-real-date'), null);
});

test('formatDate: a falsy input returns null', () => {
  assert.equal(formatDate(''), null);
  assert.equal(formatDate(null), null);
  assert.equal(formatDate(undefined), null);
});

test('formatDate: a valid iso string still formats', () => {
  assert.equal(typeof formatDate('2026-01-15T00:00:00Z'), 'string');
});
