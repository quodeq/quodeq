import test from 'node:test';
import assert from 'node:assert/strict';
import { pct, computeOverallProgress } from './scanProgressTotals.js';

/**
 * Split from scanProgressTotals.test.js: computeOverallProgress's
 * whole-run aggregation with backend per-dim estimates.
 */

test('computeOverallProgress: trusts per-dim backend totals (incremental run)', () => {
  // Each pending dim carries its own precomputed estimate (different per
  // dim because the incremental classifier hits each fingerprint). Header
  // sums them directly — no observed-max projection needed.
  const progress = {
    projectFiles: 1682,
    currentDimension: 'security',
    dimensions: [
      { id: 'security',        state: 'running', files: { taken: 3, total: 827 } },
      { id: 'reliability',     state: 'pending', files: { taken: 0, total: 412 } },
      { id: 'maintainability', state: 'pending', files: { taken: 0, total: 950 } },
      { id: 'performance',     state: 'pending', files: { taken: 0, total: 120 } },
      { id: 'usability',       state: 'pending', files: { taken: 0, total: 60 } },
      { id: 'flexibility',     state: 'pending', files: { taken: 0, total: 200 } },
    ],
  };
  const expected = 827 + 412 + 950 + 120 + 60 + 200;
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, expected);
  assert.equal(r.takenFiles, 3);
  assert.equal(r.overallPct, pct(3, expected));
});

test('computeOverallProgress: sums actual totals across multiple running/done dims', () => {
  const progress = {
    projectFiles: 1682,
    currentDimension: 'security',
    dimensions: [
      { id: 'security',    state: 'running', files: { taken: 55,  total: 2035 } },
      { id: 'reliability', state: 'running', files: { taken: 999, total: 999 } },
      { id: 'performance', state: 'pending', files: { taken: 0,   total: 800 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 2035 + 999 + 800);
  assert.equal(r.takenFiles, 55 + 999);
  assert.equal(r.overallPct, pct(1054, 3834));
});

test('computeOverallProgress: completed run reads 100%', () => {
  const progress = {
    projectFiles: 1682,
    currentDimension: null,
    dimensions: [
      { id: 'security',    state: 'done', files: { taken: 827, total: 827 } },
      { id: 'reliability', state: 'done', files: { taken: 200, total: 200 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 1027);
  assert.equal(r.takenFiles, 1027);
  assert.equal(r.overallPct, 100);
});

test('computeOverallProgress: single-dim run reads the dim directly', () => {
  const progress = {
    projectFiles: 500,
    currentDimension: 'security',
    dimensions: [
      { id: 'security', state: 'running', files: { taken: 120, total: 500 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 500);
  assert.equal(r.takenFiles, 120);
  assert.equal(r.overallPct, 24);
});

test('computeOverallProgress: running dim with zero total yields 0% (avoid div-by-zero)', () => {
  const progress = {
    projectFiles: 0,
    currentDimension: 'x',
    dimensions: [
      { id: 'x', state: 'running', files: { taken: 0, total: 0 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 0);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: ignores currentDimension (whole-run sum)', () => {
  const progress = {
    projectFiles: 200,
    currentDimension: 'ghost',
    dimensions: [
      { id: 'security', state: 'running', files: { taken: 5, total: 100 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 100);
  assert.equal(r.takenFiles, 5);
  assert.equal(r.overallPct, 5);
});

test('computeOverallProgress: running dim is shown even when other pending dims lack estimates', () => {
  // Once any dim is running, "preparing…" would contradict what's
  // visibly happening. Pending dims with no estimate just contribute 0
  // to the header sum and join later when their estimate lands.
  const progress = {
    projectFiles: 1682,
    currentDimension: 'security',
    dimensions: [
      { id: 'security',    state: 'running', files: { taken: 10, total: 827 } },
      { id: 'reliability', state: 'pending', files: { taken: 0,  total: 0 } },
      { id: 'performance', state: 'pending', files: { taken: 0,  total: 0 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 827);
  assert.equal(r.takenFiles, 10);
});

test('computeOverallProgress: setup phase shows preparing only when nothing is known', () => {
  // No dim has started, no dim has a total → still preparing.
  const progress = {
    projectFiles: 200,
    dimensions: [
      { id: 'a', state: 'pending', files: { taken: 0, total: 0 } },
      { id: 'b', state: 'pending', files: { taken: 0, total: 0 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 0);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: pending dim with estimate exits preparing', () => {
  // Backend wrote dim_estimates but no dim has started yet — header
  // still shows the projected total (no contradiction with reality).
  const progress = {
    projectFiles: 200,
    dimensions: [
      { id: 'a', state: 'pending', files: { taken: 0, total: 100 } },
      { id: 'b', state: 'pending', files: { taken: 0, total: 50 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 150);
  assert.equal(r.takenFiles, 0);
});

test('computeOverallProgress: completed run with no pending dims still sums', () => {
  // Edge case: a legacy completed run never had dim_estimates.json, but
  // all dims are done (real queue totals). The "pending=0 → preparing"
  // guard only fires for *pending* dims, so done dims aggregate normally.
  const progress = {
    projectFiles: 1682,
    dimensions: [
      { id: 'security',    state: 'done', files: { taken: 50, total: 50 } },
      { id: 'reliability', state: 'done', files: { taken: 0,  total: 0 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 50);
  assert.equal(r.takenFiles, 50);
  assert.equal(r.overallPct, 100);
});
