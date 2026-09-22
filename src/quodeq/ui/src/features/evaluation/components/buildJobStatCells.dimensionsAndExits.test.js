import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildJobStatCells,
  buildDimensionCycle,
  sumSeverities,
  formatSevHint,
  deriveScanMode,
} from './buildJobStatCells.js';

// Split from buildJobStatCells.test.js: buildDimensionCycle /
// sumSeverities / formatSevHint / deriveScanMode, and the
// buildJobStatCells time-limit-exit tests.

const baseInputs = {
  overallPct: 62,
  takenFiles: 138,
  totalFiles: 220,
  elapsedS: 134,         // 2m 14s
  liveCount: 2,
};

// ---------------------------------------------------------------------------
// buildDimensionCycle / sumSeverities / formatSevHint / deriveScanMode
// ---------------------------------------------------------------------------

const cycleProgress = {
  currentDimension: 'reliability',
  dimensions: [
    { id: 'reliability', state: 'running' },
    { id: 'usability', state: 'pending' },
    { id: 'clean-architecture', state: 'pending' },
  ],
};

test('buildDimensionCycle: running dim, 1-based index, next pending dim', () => {
  assert.deepEqual(buildDimensionCycle(cycleProgress), {
    current: 'reliability', index: 1, count: 3, next: 'usability',
  });
});

test('buildDimensionCycle: falls back to done-count when nothing is running', () => {
  const progress = {
    dimensions: [
      { id: 'a', state: 'done' },
      { id: 'b', state: 'pending' },
    ],
  };
  assert.deepEqual(buildDimensionCycle(progress), {
    current: 'b', index: 2, count: 2, next: null,
  });
});

test('buildDimensionCycle: null without dimensions', () => {
  assert.equal(buildDimensionCycle(null), null);
  assert.equal(buildDimensionCycle({ dimensions: [] }), null);
});

test('sumSeverities: buckets across dimensions, ignores unknown severities', () => {
  const counts = sumSeverities({
    reliability: [{ severity: 'critical' }, { severity: 'major' }, { severity: 'weird' }],
    usability: [{ severity: 'MAJOR' }, { severity: 'minor' }],
  });
  assert.deepEqual(counts, { critical: 1, major: 2, minor: 1 });
});

test('formatSevHint: omits zero buckets, "none yet" when empty', () => {
  assert.equal(formatSevHint({ critical: 1, major: 4, minor: 0 }), '1 critical · 4 major');
  assert.equal(formatSevHint({ critical: 0, major: 0, minor: 0 }), 'none yet');
  assert.equal(formatSevHint(null), 'none yet');
});

test('deriveScanMode: incremental with cached files, clean scan without', () => {
  const dim = (cached) => ({
    id: 'a', state: 'running',
    files: { taken: 1, total: 10 },
    filesCached: cached, filesProjectTotal: 100,
  });
  assert.equal(deriveScanMode({ dimensions: [dim(40)] }), 'incremental');
  assert.equal(deriveScanMode({ dimensions: [dim(0)] }), 'clean');
});

test('deriveScanMode: null when coverage is unknown', () => {
  assert.equal(deriveScanMode(null), null);
  assert.equal(deriveScanMode({ dimensions: [{ id: 'a', state: 'running', files: { taken: 1, total: 10 } }] }), null);
});

// ---------------------------------------------------------------------------
// buildJobStatCells: time-limit exits
// ---------------------------------------------------------------------------

test('buildJobStatCells: deadline-cancelled job reads time limit reached, not user cancelled', () => {
  const cells = buildJobStatCells('cancelled', { ...baseInputs, exitReason: 'deadline' });
  assert.equal(cells[0].label, 'STATUS');
  assert.equal(cells[0].hint, 'time limit reached');
  assert.equal(cells[0].tone, 'default');
});

test('buildJobStatCells: failed job with time_limit reason softens tone and hint', () => {
  const cells = buildJobStatCells('failed', { ...baseInputs, exitReason: 'time_limit' });
  assert.equal(cells[0].hint, 'time limit reached');
  assert.equal(cells[0].tone, 'default');
});

test('buildJobStatCells: plain cancelled still reads user cancelled', () => {
  const cells = buildJobStatCells('cancelled', baseInputs);
  assert.equal(cells[0].hint, 'user cancelled');
});

test('buildJobStatCells: plain failed keeps critical tone and see-logs hint', () => {
  const cells = buildJobStatCells('failed', baseInputs);
  assert.equal(cells[0].hint, 'see logs');
  assert.equal(cells[0].tone, 'critical');
});
