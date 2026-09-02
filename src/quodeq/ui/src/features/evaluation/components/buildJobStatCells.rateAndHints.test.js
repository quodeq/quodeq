import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildJobStatCells,
  formatRate,
  formatEta,
  buildEtaHint,
  msUntilNextSecond,
  suppressedSuffix,
  carriedSuffix,
} from './buildJobStatCells.js';

// Split from buildJobStatCells.test.js: formatRate/formatEta, buildEtaHint
// + the ELAPSED cell wiring, msUntilNextSecond, and the suppressed /
// carried-forward violation-count hints.

const baseInputs = {
  overallPct: 62,
  takenFiles: 138,
  totalFiles: 220,
  elapsedS: 134,         // 2m 14s
  liveCount: 2,
};

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
