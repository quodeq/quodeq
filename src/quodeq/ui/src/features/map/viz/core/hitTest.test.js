import test from 'node:test';
import assert from 'node:assert/strict';
import { withinRadius } from './hitTest.js';

test('withinRadius is true strictly inside the circle', () => {
  assert.deepEqual([withinRadius(3, 4, 0, 0, 6), withinRadius(10, 10, 10, 10, 1)], [true, true]);
});

test('withinRadius is false on the rim and outside', () => {
  assert.deepEqual([withinRadius(3, 4, 0, 0, 5), withinRadius(30, 4, 0, 0, 5)], [false, false]);
});
