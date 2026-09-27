import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeCountDeltas } from './historyCountDeltas.js';

const r = (majors, openTypes) => ({ dimensionDetails: majors === null ? [] : [{ majors, openTypes }] });

test('count deltas compare each row with the next row that has counts', () => {
  const deltas = computeCountDeltas([r(3, 30), r(5, 33), r(4, 33)]);
  assert.deepEqual(deltas, [{ majors: -2, openTypes: -3 }, { majors: 1, openTypes: 0 }, { majors: null, openTypes: null }]);
});

test('count deltas skip rows without counts', () => {
  const deltas = computeCountDeltas([r(3, 30), r(null, null), r(5, 33)]);
  assert.deepEqual(deltas, [{ majors: -2, openTypes: -3 }, { majors: null, openTypes: null }, { majors: null, openTypes: null }]);
});
