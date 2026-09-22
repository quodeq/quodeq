import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildJobStatCells,
  deriveRunElapsedS,
  computeRate,
  RATE_WINDOW_MS,
} from './buildJobStatCells.js';

// Split from buildJobStatCells.test.js: deriveRunElapsedS, the base
// buildJobStatCells cell-shape tests, and computeRate.

const baseInputs = {
  overallPct: 62,
  takenFiles: 138,
  totalFiles: 220,
  elapsedS: 134,         // 2m 14s
  liveCount: 2,
};

// ---------------------------------------------------------------------------
// deriveRunElapsedS
// ---------------------------------------------------------------------------

const T0 = Date.parse('2026-06-08T10:00:00Z');

test('deriveRunElapsedS: running — server elapsed extrapolated by time since the poll', () => {
  const s = deriveRunElapsedS({
    running: true, serverElapsedS: 134, serverUpdatedAtMs: T0 - 1500, nowMs: T0,
    startedAt: null, endedAt: null,
  });
  assert.equal(s, 135.5);
});

test('deriveRunElapsedS: server elapsed wins over job wall-clock timestamps (skew immunity)', () => {
  // Client thinks the run started 5s ago; server says 9999s. Server wins.
  const s = deriveRunElapsedS({
    running: true, serverElapsedS: 9999, serverUpdatedAtMs: T0, nowMs: T0,
    startedAt: new Date(T0 - 5000).toISOString(), endedAt: null,
  });
  assert.equal(s, 9999);
});

test('deriveRunElapsedS: non-running freezes on the server value, no extrapolation', () => {
  const s = deriveRunElapsedS({
    running: false, serverElapsedS: 272, serverUpdatedAtMs: T0 - 60000, nowMs: T0,
    startedAt: null, endedAt: null,
  });
  assert.equal(s, 272);
});

test('deriveRunElapsedS: falls back to job timestamps before any progress payload', () => {
  const running = deriveRunElapsedS({
    running: true, serverElapsedS: undefined, serverUpdatedAtMs: undefined, nowMs: T0,
    startedAt: new Date(T0 - 5000).toISOString(), endedAt: null,
  });
  assert.equal(running, 5);
  const ended = deriveRunElapsedS({
    running: false, serverElapsedS: null, serverUpdatedAtMs: undefined, nowMs: T0,
    startedAt: new Date(T0 - 90000).toISOString(), endedAt: new Date(T0 - 30000).toISOString(),
  });
  assert.equal(ended, 60);
});

test('deriveRunElapsedS: null when nothing is knowable, clamped at 0 for clock regressions', () => {
  assert.equal(deriveRunElapsedS({ running: true, nowMs: T0, startedAt: null, endedAt: null }), null);
  assert.equal(deriveRunElapsedS({ running: true, nowMs: T0, startedAt: 'not-a-date', endedAt: null }), null);
  const s = deriveRunElapsedS({
    running: true, serverElapsedS: undefined, nowMs: T0,
    startedAt: new Date(T0 + 5000).toISOString(), endedAt: null,
  });
  assert.equal(s, 0);
});

// ---------------------------------------------------------------------------
// buildJobStatCells
// ---------------------------------------------------------------------------

test('buildJobStatCells: builds 4 cells for a running job with progress data', () => {
  const cells = buildJobStatCells('running', {
    ...baseInputs,
    dimCycle: { current: 'reliability', index: 1, count: 3, next: 'usability' },
    scanMode: 'incremental',
  });
  assert.equal(cells.length, 4);
  assert.equal(cells[0].label, 'analyzing');
  assert.equal(cells[0].value, 'reliability');
  assert.equal(cells[0].hint, 'dim 1/3 · next: usability');
  assert.equal(cells[0].tone, 'accent');
  assert.equal(cells[1].label, 'files this run');
  assert.equal(cells[1].value, 138);
  assert.equal(cells[1].trailing, '/ 220');
  assert.equal(cells[1].hint, '62% · changed since last scan');
  assert.equal(cells[2].label, 'violations');
  assert.equal(cells[2].value, 2);
  assert.equal(cells[2].tone, 'critical');
  assert.equal(cells[3].label, 'elapsed');
  assert.equal(cells[3].value, '2m 14s');
});

test('buildJobStatCells: running analyzing tile falls back while dims are unknown', () => {
  const cells = buildJobStatCells('running', baseInputs);
  assert.equal(cells[0].label, 'analyzing');
  assert.equal(cells[0].value, '—');
  assert.equal(cells[0].hint, 'preparing…');
});

test('buildJobStatCells: running last dimension keeps the counter and drops the next hint', () => {
  const cells = buildJobStatCells('running', {
    ...baseInputs,
    dimCycle: { current: 'usability', index: 3, count: 3, next: null },
  });
  assert.equal(cells[0].label, 'analyzing');
  assert.equal(cells[0].hint, 'dim 3/3');
});

test('buildJobStatCells: running files hint omits mode copy when mode is unknown', () => {
  const cells = buildJobStatCells('running', baseInputs);
  assert.equal(cells[1].hint, '62%');
});

test('buildJobStatCells: running files hint says full rescan on clean scans', () => {
  const cells = buildJobStatCells('running', { ...baseInputs, scanMode: 'clean' });
  assert.equal(cells[1].hint, '62% · full rescan');
});

test('buildJobStatCells: running violations hint reports severity buckets', () => {
  const cells = buildJobStatCells('running', {
    ...baseInputs,
    sevCounts: { critical: 1, major: 4, minor: 0 },
  });
  assert.equal(cells[2].hint, '1 critical · 4 major');
});

test('buildJobStatCells: builds done-state cells with SCANNED + VIOLATIONS + DURATION', () => {
  const cells = buildJobStatCells('done', { ...baseInputs, takenFiles: 220, liveCount: 13, elapsedS: 272 });
  assert.equal(cells[0].label, 'STATUS');
  assert.equal(cells[0].value, 'done');
  assert.equal(cells[0].tone, 'success');
  assert.equal(cells[0].hint, null);   // when violations exist, hint stays out of the way
  assert.equal(cells[1].label, 'SCANNED');
  assert.equal(cells[1].value, 220);
  assert.equal(cells[2].label, 'VIOLATIONS');
  assert.equal(cells[2].value, 13);
  assert.equal(cells[2].tone, 'critical');
  assert.equal(cells[3].label, 'DURATION');
  assert.equal(cells[3].value, '4m 32s');
});

test('buildJobStatCells: uses correct tone for STATUS by status', () => {
  assert.equal(buildJobStatCells('done',      baseInputs)[0].tone, 'success');
  assert.equal(buildJobStatCells('completed', baseInputs)[0].tone, 'success');
  assert.equal(buildJobStatCells('failed',    baseInputs)[0].tone, 'critical');
  assert.equal(buildJobStatCells('lost',      baseInputs)[0].tone, 'critical');
  assert.equal(buildJobStatCells('cancelled', baseInputs)[0].tone, 'default');
});

test('buildJobStatCells: FOUND/VIOLATIONS cell tone is default when liveCount is 0', () => {
  const running = buildJobStatCells('running', { ...baseInputs, liveCount: 0 });
  const done    = buildJobStatCells('done',    { ...baseInputs, liveCount: 0 });
  assert.equal(running[2].tone, 'default');
  assert.equal(done[2].tone, 'default');
});

test('buildJobStatCells: renders "—" for missing data', () => {
  const cells = buildJobStatCells('running', {
    overallPct: 0, takenFiles: 0, totalFiles: 0, elapsedS: null, liveCount: 0,
  });
  assert.equal(cells[1].value, '—');   // PROGRESS — no data yet
  assert.equal(cells[3].value, '—');   // ELAPSED — no data yet
});

test('buildJobStatCells: failed/cancelled show PROGRESS + FOUND-so-far + ELAPSED', () => {
  const failed = buildJobStatCells('failed', baseInputs);
  assert.equal(failed[1].label, 'PROGRESS');
  assert.equal(failed[2].label, 'FOUND');
  assert.equal(failed[3].label, 'ELAPSED');
});

// ---------------------------------------------------------------------------
// computeRate (sliding-window throughput)
// ---------------------------------------------------------------------------

test('computeRate: files/sec from oldest→newest over the window', () => {
  // 30 files over 60s = 0.5 files/s (returned in files/sec; displayed per-min)
  const s = [{ t: 1_000_000, taken: 10 }, { t: 1_060_000, taken: 40 }];
  assert.equal(computeRate(s), 0.5);
});

test('computeRate: null when fewer than 2 samples', () => {
  assert.equal(computeRate([]), null);
  assert.equal(computeRate([{ t: 1, taken: 5 }]), null);
  assert.equal(computeRate(null), null);
});

test('computeRate: null when window span is below the minimum (~30s)', () => {
  // 10s span -> not enough to be honest yet
  const s = [{ t: 1_000_000, taken: 10 }, { t: 1_010_000, taken: 30 }];
  assert.equal(computeRate(s), null);
});

test('computeRate: null when files have not advanced (stalled)', () => {
  const s = [{ t: 1_000_000, taken: 50 }, { t: 1_040_000, taken: 50 }];
  assert.equal(computeRate(s), null);
});

test('RATE_WINDOW_MS is exported for the buffer to window against', () => {
  assert.equal(typeof RATE_WINDOW_MS, 'number');
  assert.ok(RATE_WINDOW_MS > 0);
});
