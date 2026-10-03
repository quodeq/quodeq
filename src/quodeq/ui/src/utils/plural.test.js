import test from 'node:test';
import assert from 'node:assert/strict';
import { pluralKey } from './plural.js';

test('pluralKey picks the singular key only for exactly one', () => {
  assert.equal(pluralKey(1, 'x.one', 'x.many'), 'x.one');
  assert.equal(pluralKey(0, 'x.one', 'x.many'), 'x.many');
  assert.equal(pluralKey(2, 'x.one', 'x.many'), 'x.many');
});
