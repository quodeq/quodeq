import test from 'node:test';
import assert from 'node:assert/strict';
import { pct, computeOverallProgress } from './scanProgressTotals.js';

/**
 * Split from scanProgressTotals.test.js: computeOverallProgress's total
 * project coverage (incremental runs) and excluded-files (API size cap)
 * aggregation.
 */

test('computeOverallProgress: aggregates coverage when all dims carry the fields', () => {
  // 100-file project per dim, 80 cached, this run 20; 8 taken so far.
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security',    state: 'running', files: { taken: 8, total: 20 },
        filesCached: 80, filesProjectTotal: 100 },
      { id: 'reliability', state: 'pending', files: { taken: 0, total: 10 },
        filesCached: 90, filesProjectTotal: 100 },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 30);
  assert.equal(r.takenFiles, 8);
  assert.equal(r.projectTotal, 200);
  assert.equal(r.cachedFiles, 170);
  assert.equal(r.coveredFiles, 178);
  assert.equal(r.coveredPct, pct(178, 200));
});

test('computeOverallProgress: coverage is null when any dim lacks the fields (legacy run)', () => {
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security',    state: 'running', files: { taken: 8, total: 20 },
        filesCached: 80, filesProjectTotal: 100 },
      { id: 'reliability', state: 'pending', files: { taken: 0, total: 10 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.projectTotal, null);
  assert.equal(r.cachedFiles, null);
  assert.equal(r.coveredFiles, null);
  assert.equal(r.coveredPct, null);
  // Run-relative aggregation untouched.
  assert.equal(r.totalFiles, 30);
  assert.equal(r.takenFiles, 8);
});

test('computeOverallProgress: full scan aggregates with zero cached', () => {
  const progress = {
    projectFiles: 60,
    dimensions: [
      { id: 'security', state: 'running', files: { taken: 12, total: 60 },
        filesCached: 0, filesProjectTotal: 60 },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.projectTotal, 60);
  assert.equal(r.cachedFiles, 0);
  assert.equal(r.coveredFiles, 12);
  assert.equal(r.coveredPct, 20);
});

test('computeOverallProgress: covered files clamp to project total on overshoot', () => {
  // filesCached/filesProjectTotal are frozen at estimate time while
  // files.taken comes from the live queue — files changing on disk in
  // between can push cached+taken past the frozen total. Never render
  // "105 / 100".
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security', state: 'running', files: { taken: 30, total: 30 },
        filesCached: 80, filesProjectTotal: 100 },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.coveredFiles, 100);
  assert.equal(r.coveredPct, 100);
});

test('computeOverallProgress: completed incremental run reads full coverage', () => {
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security', state: 'done', files: { taken: 20, total: 20 },
        filesCached: 80, filesProjectTotal: 100 },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.coveredFiles, 100);
  assert.equal(r.coveredPct, 100);
});

test('computeOverallProgress: excludedFiles is the max across dims, not the sum', () => {
  // The size cap is dim-agnostic: every dim reports the same excluded
  // count. Summing would multiply it by the number of dims.
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security',    state: 'running', files: { taken: 8, total: 20 },
        filesCached: 80, filesProjectTotal: 100, filesExcluded: 3 },
      { id: 'reliability', state: 'pending', files: { taken: 0, total: 10 },
        filesCached: 90, filesProjectTotal: 100, filesExcluded: 3 },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.excludedFiles, 3);
});

test('computeOverallProgress: excludedFiles is null when no dim carries the field (legacy run)', () => {
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security', state: 'running', files: { taken: 8, total: 20 },
        filesCached: 80, filesProjectTotal: 100 },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.excludedFiles, null);
});

test('computeOverallProgress: excludedFiles is 0 when dims report zero excluded', () => {
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security', state: 'running', files: { taken: 8, total: 20 },
        filesCached: 80, filesProjectTotal: 100, filesExcluded: 0 },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.excludedFiles, 0);
});

test('computeOverallProgress: excludedFiles reads the dims that carry it when others lack it', () => {
  // Mixed payload (e.g. a dim added mid-rollout): use whatever is known.
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security',    state: 'running', files: { taken: 8, total: 20 },
        filesCached: 80, filesProjectTotal: 100, filesExcluded: 5 },
      { id: 'reliability', state: 'pending', files: { taken: 0, total: 10 } },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.excludedFiles, 5);
});

test('computeOverallProgress: excludedFiles is null when progress is null or empty', () => {
  assert.equal(computeOverallProgress(null).excludedFiles, null);
  assert.equal(computeOverallProgress({ dimensions: [] }).excludedFiles, null);
});

test('computeOverallProgress: fully-cached re-scan keeps coverage despite empty queues', () => {
  // Nothing changed since the last run: every dim is done with a zero
  // queue. The run-relative sum is empty, but coverage data is still
  // present — the whole project is covered by cache.
  const progress = {
    projectFiles: 100,
    dimensions: [
      { id: 'security', state: 'done', files: { taken: 0, total: 0 },
        filesCached: 100, filesProjectTotal: 100 },
    ],
  };
  const r = computeOverallProgress(progress);
  assert.equal(r.totalFiles, 0);
  assert.equal(r.projectTotal, 100);
  assert.equal(r.cachedFiles, 100);
  assert.equal(r.coveredFiles, 100);
  assert.equal(r.coveredPct, 100);
});
