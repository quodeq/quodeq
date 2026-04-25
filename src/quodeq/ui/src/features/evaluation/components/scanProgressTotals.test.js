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
  const r = computeOverallProgress({
    projectFiles: 50,
    dimensions: [{ id: 'x', state: 'pending' }],
  });
  // Pending dim with no observed sibling → fallback estimate is projectFiles.
  assert.equal(r.totalFiles, 50);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});

// ---------------------------------------------------------------------------
// computeOverallProgress — aggregated headline
// ---------------------------------------------------------------------------

test('computeOverallProgress: 2 dims × 100 files reads "X / 200" (aggregated)', () => {
  // Header is the aggregated work across dims, not the project file
  // count. Two dims that each scan 100 files = 200 work units.
  const progress = {
    projectFiles: 100,
    dimensions: [
      { state: 'running', files: { taken: 50, total: 100 } },
      { state: 'pending', files: { taken: 0,  total: 100 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 200);
  assert.equal(r.takenFiles, 50);
  assert.equal(r.overallPct, 25);
});

test('computeOverallProgress: 6-dim run does NOT use project-ceiling for pending dims (regression)', () => {
  // Reproduces the bug from the screenshot. Without the fallback
  // substitution, pending dims would each contribute the project-wide
  // ceiling (1682) and the headline becomes "3 / 9237 files". With the
  // substitution, every dim contributes the post-filter queue size (827)
  // observed on the running dim, and the headline becomes the coherent
  // aggregated "3 / 4962 files".
  const progress = {
    projectFiles: 1682,
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
  assert.equal(r.totalFiles, 4962, 'pending dims contribute 827 each, not 1682');
  assert.equal(r.takenFiles, 3);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: pending dims before any has started fall back to projectFiles', () => {
  // Every dim is pending — no observed running/done queue total exists,
  // so the only sensible fallback is projectFiles (the upper bound).
  const progress = {
    projectFiles: 200,
    dimensions: [
      { state: 'pending', files: { taken: 0, total: 200 } },
      { state: 'pending', files: { taken: 0, total: 200 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 400);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: single-dim run keeps the per-dim count intact', () => {
  const progress = {
    projectFiles: 500,
    dimensions: [
      { state: 'running', files: { taken: 120, total: 500 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 500);
  assert.equal(r.takenFiles, 120);
  assert.equal(r.overallPct, 24);
});

test('computeOverallProgress: all dims done → 100% and full aggregated count', () => {
  const progress = {
    projectFiles: 200,
    dimensions: [
      { state: 'done', files: { taken: 200, total: 200 } },
      { state: 'done', files: { taken: 200, total: 200 } },
      { state: 'done', files: { taken: 200, total: 200 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 600);
  assert.equal(r.takenFiles, 600);
  assert.equal(r.overallPct, 100);
});

test('computeOverallProgress: zero workTotal yields 0% (avoid div-by-zero)', () => {
  const progress = {
    projectFiles: 0,
    dimensions: [
      { state: 'pending', files: { taken: 0, total: 0 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 0);
  assert.equal(r.takenFiles, 0);
  assert.equal(r.overallPct, 0);
});

test('computeOverallProgress: mixed running queues contribute their own totals', () => {
  // Two running dims with different post-filter queues — each contributes
  // its actual queue total to the aggregate; only pending dims get the
  // fallback estimate (which here is the larger of the two running totals).
  const progress = {
    projectFiles: 200,
    dimensions: [
      { state: 'running', files: { taken: 30, total: 100 } },
      { state: 'running', files: { taken: 80, total: 150 } },
      { state: 'pending', files: { taken: 0,  total: 200 } },
    ],
  };
  const r = computeOverallProgress(progress);
  // 100 (running) + 150 (running) + 150 (pending → fallback = max observed)
  assert.equal(r.totalFiles, 400);
  assert.equal(r.takenFiles, 110);
  assert.equal(r.overallPct, 28);
});
