import test from 'node:test';
import assert from 'node:assert/strict';
import { formatSize } from './formatSize.js';

test('formatSize shows one decimal in MB from 1 MB up', () => {
  assert.equal(formatSize(12582912), '12.0 MB');
  assert.equal(formatSize(1048576), '1.0 MB');
});

test('formatSize shows whole KB below 1 MB, never 0 KB for a non-empty count', () => {
  assert.equal(formatSize(2048), '2 KB');
  assert.equal(formatSize(10), '1 KB');
});

test('formatSize is null without a count yet', () => {
  assert.equal(formatSize(null), null);
  assert.equal(formatSize(undefined), null);
  assert.equal(formatSize(-1), null);
  assert.equal(formatSize(0), null);
});
