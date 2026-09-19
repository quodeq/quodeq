import test from 'node:test';
import assert from 'node:assert/strict';
import { filterValidRefs } from './reqRefs.js';

test('filterValidRefs keeps only refs with an http(s) url', () => {
  const refs = [{ url: 'https://a' }, { url: 'ftp://b' }, { label: 'c' }, null];
  assert.deepEqual(filterValidRefs(refs), [{ url: 'https://a' }]);
});

test('filterValidRefs returns [] for undefined input', () => {
  assert.deepEqual(filterValidRefs(undefined), []);
});
