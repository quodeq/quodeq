import test from 'node:test';
import assert from 'node:assert/strict';
import { filterRunsByVisibleStandards } from './scoreFiltering.js';

// partialRuns (cancelled runs with their own scores) follow the visible
// standards like the trend does, but carry no accumulated score: nothing is
// walked, each entry keeps only its own recomputed average.

const RUN = {
  runId: 'c1', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z',
  runNumericAverage: 6.0, numericAverage: null,
  dimensions: ['security', 'usability'], dimensionsCount: 2,
  dimensionDetails: [
    { dimension: 'security', score: 4.0, grade: 'Poor', delta: null },
    { dimension: 'usability', score: 8.0, grade: 'Good', delta: null },
  ],
};

test('narrows the run to the visible dimensions and recomputes its own average', () => {
  const [out] = filterRunsByVisibleStandards([RUN], new Set(['security']));
  assert.equal(out.runNumericAverage, 4.0);
  assert.deepEqual(out.dimensions, ['security']);
  assert.equal(out.dimensionsCount, 1);
  assert.equal(out.numericAverage, null);
});

test('drops a run with no visible dimension', () => {
  assert.deepEqual(filterRunsByVisibleStandards([RUN], new Set(['performance'])), []);
});

test('tolerates a missing list', () => {
  assert.deepEqual(filterRunsByVisibleStandards(undefined, new Set(['security'])), []);
});
