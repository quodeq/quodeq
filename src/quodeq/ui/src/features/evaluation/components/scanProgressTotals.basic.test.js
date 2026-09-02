import test from 'node:test';
import assert from 'node:assert/strict';
import { pct, computeOverallProgress, dimFileEstimate } from './scanProgressTotals.js';

/**
 * Split from scanProgressTotals.test.js: pct, dimFileEstimate, and
 * computeOverallProgress's empty/edge cases.
 */

test('pct: returns 0 when total is 0', () => {
  assert.equal(pct(0, 0), 0);
  assert.equal(pct(5, 0), 0);
});

test('pct: returns 0 when total is undefined or negative', () => {
  assert.equal(pct(5, undefined), 0);
  assert.equal(pct(5, -1), 0);
});

test('pct: rounds to nearest integer', () => {
  assert.equal(pct(1, 3), 33);
  assert.equal(pct(2, 3), 67);
  assert.equal(pct(1, 100), 1);
});

test('pct: caps at 100 when taken > total', () => {
  assert.equal(pct(150, 100), 100);
});

test('dimFileEstimate: returns max of running/done queue totals', () => {
  const r = dimFileEstimate({
    projectFiles: 1682,
    dimensions: [
      { state: 'running', files: { taken: 3, total: 827 } },
      { state: 'done',    files: { taken: 600, total: 600 } },
      { state: 'pending', files: { taken: 0, total: 1682 } },
    ],
  });
  assert.equal(r, 827);
});

test('dimFileEstimate: falls back to projectFiles when no dim has started', () => {
  const r = dimFileEstimate({
    projectFiles: 1682,
    dimensions: [
      { state: 'pending', files: { taken: 0, total: 1682 } },
      { state: 'pending', files: { taken: 0, total: 1682 } },
    ],
  });
  assert.equal(r, 1682);
});

test('dimFileEstimate: returns 0 when nothing is known', () => {
  assert.equal(dimFileEstimate(null), 0);
  assert.equal(dimFileEstimate({}), 0);
  assert.equal(dimFileEstimate({ dimensions: [] }), 0);
});

test('computeOverallProgress: returns zeros when progress is null', () => {
  const r = computeOverallProgress(null);
  assert.deepEqual(r, {
    totalFiles: 0, takenFiles: 0, overallPct: 0,
    projectTotal: null, cachedFiles: null, coveredFiles: null, coveredPct: null,
    excludedFiles: null,
  });
});

test('computeOverallProgress: returns zeros when dimensions array is empty', () => {
  const r = computeOverallProgress({ projectFiles: 100, dimensions: [] });
  assert.equal(r.totalFiles, 0);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: setup phase (no per-dim totals yet) → zeros', () => {
  // Backend hasn't written estimates yet and no dim has started — every
  // dim's files.total is 0. Header stays in "preparing…".
  const progress = {
    projectFiles: 200,
    dimensions: [
      { id: 'a', state: 'pending', files: { taken: 0, total: 0 } },
      { id: 'b', state: 'pending', files: { taken: 0, total: 0 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 0);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: handles missing files object on a dim', () => {
  const r = computeOverallProgress({
    projectFiles: 50,
    dimensions: [{ id: 'x', state: 'pending' }],
  });
  assert.equal(r.totalFiles, 0);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});
