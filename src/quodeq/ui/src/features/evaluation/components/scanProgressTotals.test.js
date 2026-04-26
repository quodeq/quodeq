import test from 'node:test';
import assert from 'node:assert/strict';
import { pct, computeOverallProgress, dimFileEstimate } from './scanProgressTotals.js';

// ---------------------------------------------------------------------------
// pct
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// dimFileEstimate
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// computeOverallProgress — empty and edge cases
// ---------------------------------------------------------------------------

test('computeOverallProgress: returns zeros when progress is null', () => {
  const r = computeOverallProgress(null);
  assert.deepEqual(r, { totalFiles: 0, takenFiles: 0, overallPct: 0 });
});

test('computeOverallProgress: returns zeros when dimensions array is empty', () => {
  const r = computeOverallProgress({ projectFiles: 100, dimensions: [] });
  assert.equal(r.totalFiles, 0);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: handles missing files object on a dim', () => {
  // No currentDimension, no done dim, only pending → header shows zeros.
  // Pending dims never drive the header on their own (per the new contract).
  const r = computeOverallProgress({
    projectFiles: 50,
    dimensions: [{ id: 'x', state: 'pending' }],
  });
  assert.equal(r.totalFiles, 0);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});

// ---------------------------------------------------------------------------
// computeOverallProgress — current-dim headline
// ---------------------------------------------------------------------------

test('computeOverallProgress: tracks the running dim by id', () => {
  // currentDimension picks security; reliability is also running but ignored.
  const progress = {
    projectFiles: 1682,
    currentDimension: 'security',
    dimensions: [
      { id: 'security',    state: 'running', files: { taken: 55, total: 2035 } },
      { id: 'reliability', state: 'running', files: { taken: 999, total: 999 } },
      { id: 'performance', state: 'pending', files: { taken: 0,  total: 1682 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 2035);
  assert.equal(r.takenFiles, 55);
  assert.equal(r.overallPct, 3);
});

test('computeOverallProgress: pending dim fallback ceiling does NOT leak into header (regression)', () => {
  // Reproduces the screenshot bug: 6-dim incremental run with one running
  // (security, 827 changed files) and five pending. Old aggregation summed
  // them and produced a misleading total. New contract: header tracks only
  // security.
  const progress = {
    projectFiles: 1682,
    currentDimension: 'security',
    dimensions: [
      { id: 'security',        state: 'running', files: { taken: 3, total: 827 } },
      { id: 'reliability',     state: 'pending', files: { taken: 0, total: 1682 } },
      { id: 'maintainability', state: 'pending', files: { taken: 0, total: 1682 } },
      { id: 'performance',     state: 'pending', files: { taken: 0, total: 1682 } },
      { id: 'usability',       state: 'pending', files: { taken: 0, total: 1682 } },
      { id: 'flexibility',     state: 'pending', files: { taken: 0, total: 1682 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 827, 'header is just security, not summed');
  assert.equal(r.takenFiles, 3);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: falls back to first running dim when currentDimension is unset', () => {
  // Race window between dim transitions: a dim is running but the backend
  // hasn't set currentDimension yet.
  const progress = {
    projectFiles: 1682,
    currentDimension: null,
    dimensions: [
      { id: 'security',    state: 'pending', files: { taken: 0, total: 1682 } },
      { id: 'reliability', state: 'running', files: { taken: 7, total: 200 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 200);
  assert.equal(r.takenFiles, 7);
  assert.equal(r.overallPct, 4);
});

test('computeOverallProgress: falls back to last done dim when run has finished', () => {
  // After completion, currentDimension is null and no dim is running.
  // We surface the last completed dim so the header reads a real 100%
  // instead of 0/0.
  const progress = {
    projectFiles: 1682,
    currentDimension: null,
    dimensions: [
      { id: 'security',    state: 'done', files: { taken: 827, total: 827 } },
      { id: 'reliability', state: 'done', files: { taken: 200, total: 200 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 200, 'last done dim wins');
  assert.equal(r.takenFiles, 200);
  assert.equal(r.overallPct, 100);
});

test('computeOverallProgress: setup phase (all pending) → zeros', () => {
  // Before any dim has started: no current, no running, no done. The header
  // shows preparing… per the JSX guard, which expects totalFiles: 0.
  const progress = {
    projectFiles: 200,
    currentDimension: null,
    dimensions: [
      { id: 'a', state: 'pending', files: { taken: 0, total: 200 } },
      { id: 'b', state: 'pending', files: { taken: 0, total: 200 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 0);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
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

test('computeOverallProgress: zero workTotal on running dim yields 0% (avoid div-by-zero)', () => {
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

test('computeOverallProgress: currentDimension that does not match any dim falls back gracefully', () => {
  // Defensive: backend hiccup where currentDimension references a dim that
  // isn't in the array. Fall through to the running-dim fallback.
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
