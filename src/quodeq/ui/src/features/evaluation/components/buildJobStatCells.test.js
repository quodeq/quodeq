import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildJobStatCells,
  formatClock,
  computeRate,
  RATE_WINDOW_MS,
  formatRate,
  formatEta,
  buildEtaHint,
  msUntilNextSecond,
  suppressedSuffix,
  carriedSuffix,
  buildDimensionCycle,
  sumSeverities,
  formatSevHint,
  deriveScanMode,
} from './buildJobStatCells.js';

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
  const cells = buildJobStatCells('running', {
    ...baseInputs,
    dimCycle: { current: 'reliability', index: 1, count: 3, next: 'usability' },
    scanMode: 'incremental',
  });
  assert.equal(cells.length, 4);
  assert.equal(cells[0].label, 'analyzing · dimension 1 / 3');
  assert.equal(cells[0].value, 'reliability');
  assert.equal(cells[0].hint, 'next: usability');
  assert.equal(cells[0].tone, 'accent');
  assert.equal(cells[1].label, 'files this run');
  assert.equal(cells[1].value, 138);
  assert.equal(cells[1].trailing, '/ 220');
  assert.equal(cells[1].hint, '62% · changed since last scan');
  assert.equal(cells[2].label, 'violations');
  assert.equal(cells[2].value, 2);
  assert.equal(cells[2].tone, 'critical');
  assert.equal(cells[3].label, 'elapsed');
  assert.equal(cells[3].value, '2:14');
});

test('buildJobStatCells: running analyzing tile falls back while dims are unknown', () => {
  const cells = buildJobStatCells('running', baseInputs);
  assert.equal(cells[0].label, 'analyzing');
  assert.equal(cells[0].value, '—');
  assert.equal(cells[0].hint, 'preparing…');
});

test('buildJobStatCells: running last dimension says so instead of a next hint', () => {
  const cells = buildJobStatCells('running', {
    ...baseInputs,
    dimCycle: { current: 'usability', index: 3, count: 3, next: null },
  });
  assert.equal(cells[0].label, 'analyzing · dimension 3 / 3');
  assert.equal(cells[0].hint, 'last dimension');
});

test('buildJobStatCells: running files hint omits mode copy when mode is unknown', () => {
  const cells = buildJobStatCells('running', baseInputs);
  assert.equal(cells[1].hint, '62%');
});

test('buildJobStatCells: running files hint says full rescan on clean scans', () => {
  const cells = buildJobStatCells('running', { ...baseInputs, scanMode: 'clean scan' });
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
  assert.equal(cells[3].value, '4:32');
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

test('buildJobStatCells: running elapsed cell carries the etaHint as its subtext', () => {
  const cells = buildJobStatCells('running', { ...baseInputs, etaHint: '~6 files/min · ~5h left' });
  assert.equal(cells[3].label, 'elapsed');
  assert.equal(cells[3].hint, '~6 files/min · ~5h left');
});

test('buildJobStatCells: done DURATION cell ignores etaHint', () => {
  const cells = buildJobStatCells('done', { ...baseInputs, takenFiles: 220, etaHint: 'should-not-appear' });
  assert.equal(cells[3].label, 'DURATION');
  assert.equal(cells[3].hint, 'total');
});

// ---------------------------------------------------------------------------
// msUntilNextSecond (boundary-aligned re-render delay for the ELAPSED ticker)
// ---------------------------------------------------------------------------

test('msUntilNextSecond: delay to the next whole-second boundary, in (0, 1000]', () => {
  assert.equal(msUntilNextSecond(0), 1000);      // on a boundary → a full second to the next
  assert.equal(msUntilNextSecond(5000), 1000);   // whole second elapsed
  assert.equal(msUntilNextSecond(5300), 700);    // 300ms into the second
  assert.equal(msUntilNextSecond(999), 1);       // just before the boundary
  assert.equal(msUntilNextSecond(1500), 500);
});

test('msUntilNextSecond: normalizes negatives and defaults non-finite to 1000', () => {
  assert.equal(msUntilNextSecond(-300), 300);
  assert.equal(msUntilNextSecond(NaN), 1000);
  assert.equal(msUntilNextSecond(Infinity), 1000);
});

// ---------------------------------------------------------------------------
// suppressed hint — the live counters are net, so say what was netted out
// ---------------------------------------------------------------------------

test('buildJobStatCells: violations hint reports the suppressed count while running', () => {
  const cells = buildJobStatCells('running', {
    ...baseInputs, liveCount: 122, suppressedCount: 339,
    sevCounts: { critical: 2, major: 120, minor: 0 },
  });
  assert.equal(cells[2].label, 'violations');
  assert.equal(cells[2].value, 122);
  assert.equal(cells[2].hint, '2 critical · 120 major · 339 suppressed');
});

test('buildJobStatCells: VIOLATIONS hint reports it on a finished job too', () => {
  const cells = buildJobStatCells('done', { ...baseInputs, liveCount: 146, suppressedCount: 391 });
  assert.equal(cells[2].label, 'VIOLATIONS');
  assert.ok(cells[2].hint.endsWith('391 suppressed'), `got: ${cells[2].hint}`);
});

test('buildJobStatCells: no suppressed hint on a project with nothing suppressed', () => {
  const running = buildJobStatCells('running', { ...baseInputs, suppressedCount: 0 });
  const missing = buildJobStatCells('running', baseInputs);
  assert.equal(running[2].hint, 'none yet');
  assert.equal(missing[2].hint, 'none yet');
});

test('suppressedSuffix: ignores negative and non-numeric counts', () => {
  assert.equal(suppressedSuffix(-5), '');
  assert.equal(suppressedSuffix(undefined), '');
  assert.equal(suppressedSuffix('lots'), '');
});

// ---------------------------------------------------------------------------
// carried-forward hint — the live-findings-only preference filters FOUND
// before the strip ever sees it, so say what was filtered out
// ---------------------------------------------------------------------------

test('buildJobStatCells: violations hint reports the carried-forward count while running', () => {
  const cells = buildJobStatCells('running', {
    ...baseInputs, liveCount: 1, carriedCount: 12,
    sevCounts: { critical: 0, major: 1, minor: 0 },
  });
  assert.equal(cells[2].label, 'violations');
  assert.equal(cells[2].hint, '1 major · 12 carried forward');
});

test('buildJobStatCells: VIOLATIONS hint reports the carried-forward count on a finished job too', () => {
  const cells = buildJobStatCells('done', { ...baseInputs, liveCount: 1, carriedCount: 12 });
  assert.equal(cells[2].label, 'VIOLATIONS');
  assert.ok(cells[2].hint.endsWith('12 carried forward'), `got: ${cells[2].hint}`);
});

test('buildJobStatCells: no carried-forward hint when nothing was filtered', () => {
  const running = buildJobStatCells('running', { ...baseInputs, carriedCount: 0 });
  const missing = buildJobStatCells('running', baseInputs);
  assert.equal(running[2].hint, 'none yet');
  assert.equal(missing[2].hint, 'none yet');
});

test('buildJobStatCells: suppressed and carried-forward suffixes combine', () => {
  const cells = buildJobStatCells('done', {
    ...baseInputs, liveCount: 1, suppressedCount: 5, carriedCount: 12,
  });
  assert.equal(cells[2].hint, '1 total · 5 suppressed · 12 carried forward');
});

test('carriedSuffix: ignores negative and non-numeric counts', () => {
  assert.equal(carriedSuffix(-5), '');
  assert.equal(carriedSuffix(undefined), '');
  assert.equal(carriedSuffix('lots'), '');
});

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
  assert.equal(deriveScanMode({ dimensions: [dim(0)] }), 'clean scan');
});

test('deriveScanMode: null when coverage is unknown', () => {
  assert.equal(deriveScanMode(null), null);
  assert.equal(deriveScanMode({ dimensions: [{ id: 'a', state: 'running', files: { taken: 1, total: 10 } }] }), null);
});
