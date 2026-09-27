import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeCountDeltas } from './historyCountDeltas.js';

const r = (majors, openTypes) => ({ numericAverage: majors === null ? null : '8.0', dimensionDetails: majors === null ? [] : [{ dimension: 'a', majors, openTypes }] });
const full = (a, b) => ({ numericAverage: '8.0', dimensionDetails: [{ dimension: 'a', majors: a[0], openTypes: a[1] }, { dimension: 'b', majors: b[0], openTypes: b[1] }] });

test('count deltas compare each row with the next row that has counts', () => {
  const deltas = computeCountDeltas([r(3, 30), r(5, 33), r(4, 33)]);
  assert.deepEqual(deltas, [{ majors: -2, openTypes: -3 }, { majors: 1, openTypes: 0 }, { majors: null, openTypes: null }]);
});

test('count deltas skip rows without counts', () => {
  const deltas = computeCountDeltas([r(3, 30), r(null, null), r(5, 33)]);
  assert.deepEqual(deltas, [{ majors: -2, openTypes: -3 }, { majors: null, openTypes: null }, { majors: null, openTypes: null }]);
});

test('a cancelled partial row between two full runs takes no part in their deltas', () => {
  const partial = { numericAverage: null, dimensionDetails: [{ dimension: 'a', majors: 1, openTypes: 2 }] };
  const deltas = computeCountDeltas([full([10, 20], [20, 10]), partial, full([12, 21], [20, 10])]);
  assert.deepEqual(deltas, [{ majors: -2, openTypes: -1 }, { majors: null, openTypes: null }, { majors: null, openTypes: null }]);
});

test('a run that refreshed one dimension compares over that dimension only', () => {
  const oneDim = { numericAverage: '8.0', dimensionDetails: [{ dimension: 'a', majors: 8, openTypes: 18 }] };
  const deltas = computeCountDeltas([oneDim, full([10, 20], [20, 10])]);
  assert.deepEqual(deltas[0], { majors: -2, openTypes: -2 });
});

test('rows with no shared dimension get no delta', () => {
  const onlyB = { numericAverage: '8.0', dimensionDetails: [{ dimension: 'b', majors: 1, openTypes: 1 }] };
  const onlyA = { numericAverage: '8.0', dimensionDetails: [{ dimension: 'a', majors: 5, openTypes: 5 }] };
  assert.deepEqual(computeCountDeltas([onlyB, onlyA])[0], { majors: null, openTypes: null });
});
