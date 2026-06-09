import test from 'node:test';
import assert from 'node:assert/strict';
import { buildJobStatCells, formatClock, computeRate, RATE_WINDOW_MS, formatRate, formatEta, buildEtaHint } from './buildJobStatCells.js';

const baseInputs = {
  overallPct: 62,
  takenFiles: 138,
  totalFiles: 220,
  elapsedS: 134,         // 02:14
  liveCount: 2,
};

// ---------------------------------------------------------------------------
// formatClock
// ---------------------------------------------------------------------------

test('formatClock: formats seconds as m:ss', () => {
  assert.equal(formatClock(0), '0:00');
  assert.equal(formatClock(59), '0:59');
  assert.equal(formatClock(60), '1:00');
  assert.equal(formatClock(134), '2:14');
  assert.equal(formatClock(3661), '61:01');
});

test('formatClock: returns "—" for null/undefined/non-finite', () => {
  assert.equal(formatClock(null), '—');
  assert.equal(formatClock(undefined), '—');
  assert.equal(formatClock(NaN), '—');
  assert.equal(formatClock(Infinity), '—');
});

// ---------------------------------------------------------------------------
// buildJobStatCells
// ---------------------------------------------------------------------------

test('buildJobStatCells: builds 4 cells for a running job with progress data', () => {
  const cells = buildJobStatCells('running', baseInputs);
  assert.equal(cells.length, 4);
  assert.equal(cells[0].label, 'STATUS');
  assert.equal(cells[0].value, 'running');
  assert.equal(cells[0].tone, 'warning');
  assert.equal(cells[1].label, 'PROGRESS');
  assert.equal(cells[1].value, '62%');
  assert.ok(cells[1].hint.includes('138 / 220'), `hint should contain "138 / 220", got: ${cells[1].hint}`);
  assert.equal(cells[2].label, 'FOUND');
  assert.equal(cells[2].value, 2);
  assert.equal(cells[2].tone, 'critical');
  assert.equal(cells[3].label, 'ELAPSED');
  assert.equal(cells[3].value, '2:14');
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
  assert.equal(cells[3].value, '4:32');
});

test('buildJobStatCells: uses correct tone for STATUS by status', () => {
  assert.equal(buildJobStatCells('running',   baseInputs)[0].tone, 'warning');
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

// ---------------------------------------------------------------------------
// formatRate / formatEta
// ---------------------------------------------------------------------------

test('formatRate: per-minute display (integer at/above 1/min, 1 decimal below)', () => {
  assert.equal(formatRate(0.05), '~3 files/min');      // 0.05/s = 3/min
  assert.equal(formatRate(0.1), '~6 files/min');       // 6/min
  assert.equal(formatRate(0.25), '~15 files/min');     // 15/min
  assert.equal(formatRate(1 / 600), '~0.1 files/min'); // 0.1/min keeps a decimal
});

test('formatRate: null for non-positive / non-finite / null', () => {
  assert.equal(formatRate(0), null);
  assert.equal(formatRate(-1), null);
  assert.equal(formatRate(Infinity), null);
  assert.equal(formatRate(null), null);
});

test('formatEta: "finishing" when essentially done', () => {
  assert.equal(formatEta(0, 1), 'finishing');     // nothing left
  assert.equal(formatEta(40, 1), 'finishing');    // 40s <= 45s
});

test('formatEta: minute buckets (nearest 1 under 10m, nearest 5 over)', () => {
  assert.equal(formatEta(120, 1), '~2 min left');   // 120s
  assert.equal(formatEta(1000, 1), '~15 min left'); // 1000s ≈ 16.7m -> nearest 5 = 15
  assert.equal(formatEta(50, 1), '~1 min left');    // 50s -> 1m (just over the 45s floor)
});

test('formatEta: hour buckets, minutes to nearest 5, carry at 60', () => {
  assert.equal(formatEta(18000, 1), '~5h left');        // 5h exactly
  assert.equal(formatEta(19800, 1), '~5h 30m left');    // 5h30m
  assert.equal(formatEta(7080, 1), '~2h left');         // 1h58m -> minutes round to 60 -> carry
});

test('formatEta: estimating when rate is unusable', () => {
  assert.equal(formatEta(100, 0), 'estimating…');
  assert.equal(formatEta(100, null), 'estimating…');
});

// ---------------------------------------------------------------------------
// buildEtaHint + ELAPSED cell wiring
// ---------------------------------------------------------------------------

test('buildEtaHint: null when total is unknown (preparing…)', () => {
  assert.equal(buildEtaHint({ rate: 1, takenFiles: 0, totalFiles: 0 }), null);
});

test('buildEtaHint: "estimating…" when rate is unusable but total is known', () => {
  assert.equal(buildEtaHint({ rate: null, takenFiles: 5, totalFiles: 100 }), 'estimating…');
});

test('buildEtaHint: "~rate files/min · ~eta" when estimate is available', () => {
  // 90 files left at 0.1 file/s (6/min) = 900s -> "~15 min left"
  assert.equal(
    buildEtaHint({ rate: 0.1, takenFiles: 10, totalFiles: 100 }),
    '~6 files/min · ~15 min left',
  );
});

test('buildJobStatCells: running ELAPSED cell carries the etaHint as its subtext', () => {
  const cells = buildJobStatCells('running', { ...baseInputs, etaHint: '~6 files/min · ~5h left' });
  assert.equal(cells[3].label, 'ELAPSED');
  assert.equal(cells[3].hint, '~6 files/min · ~5h left');
});

test('buildJobStatCells: done DURATION cell ignores etaHint', () => {
  const cells = buildJobStatCells('done', { ...baseInputs, takenFiles: 220, etaHint: 'should-not-appear' });
  assert.equal(cells[3].label, 'DURATION');
  assert.equal(cells[3].hint, 'total');
});
