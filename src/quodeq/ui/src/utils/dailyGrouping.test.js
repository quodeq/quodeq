import test from 'node:test';
import assert from 'node:assert/strict';
import {
  collapseByDay, collectDayDimensions, buildDailyRuns,
  bucketKey, isoWeekKey, collapseByPeriod, collectPeriodDimensions, buildPeriodRuns,
} from './dailyGrouping.js';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TREND = [
  { runId: 'r1', dateISO: '2026-03-25T14:00:00', numericAverage: 9.5, overallGrade: 'Exemplary', dimensions: ['maintainability'] },
  { runId: 'r2', dateISO: '2026-03-25T10:00:00', numericAverage: 9.3, overallGrade: 'Exemplary', dimensions: ['security'] },
  { runId: 'r3', dateISO: '2026-03-24T18:00:00', numericAverage: 9.0, overallGrade: 'Exemplary', dimensions: ['maintainability', 'reliability'] },
  { runId: 'r4', dateISO: '2026-03-24T08:00:00', numericAverage: 8.8, overallGrade: 'Good', dimensions: ['security'] },
  { runId: 'r5', dateISO: '2026-03-23T12:00:00', numericAverage: 8.5, overallGrade: 'Good', dimensions: ['maintainability'] },
];

const AVAILABLE_RUNS = [
  { runId: 'r1', dateLabel: '2026-03-25' },
  { runId: 'r2', dateLabel: '2026-03-25' },
  { runId: 'r3', dateLabel: '2026-03-24' },
  { runId: 'r4', dateLabel: '2026-03-24' },
  { runId: 'r5', dateLabel: '2026-03-23' },
];

// ---------------------------------------------------------------------------
// collapseByDay
// ---------------------------------------------------------------------------

test('collapseByDay: groups by day, keeps newest entry per day', () => {
  const result = collapseByDay(TREND);
  assert.equal(result.length, 3);
  assert.equal(result[0].runId, 'r1'); // Mar 25 newest
  assert.equal(result[1].runId, 'r3'); // Mar 24 newest
  assert.equal(result[2].runId, 'r5'); // Mar 23
});

test('collapseByDay: newest entry has correct accumulated score', () => {
  const result = collapseByDay(TREND);
  assert.equal(result[0].numericAverage, 9.5); // Mar 25 newest run's score
  assert.equal(result[1].numericAverage, 9.0); // Mar 24 newest run's score
});

test('collapseByDay: returns empty for empty input', () => {
  assert.deepEqual(collapseByDay([]), []);
  assert.deepEqual(collapseByDay(null), null);
  assert.deepEqual(collapseByDay(undefined), undefined);
});

test('collapseByDay: single entry returns as-is', () => {
  const single = [{ runId: 'x', dateISO: '2026-01-01T00:00:00' }];
  const result = collapseByDay(single);
  assert.equal(result.length, 1);
  assert.equal(result[0].runId, 'x');
});

test('collapseByDay: entries without dateISO get their own group', () => {
  const trend = [
    { runId: 'a', dateISO: '2026-03-25T10:00:00' },
    { runId: 'b', dateISO: null },
    { runId: 'c', dateISO: '2026-03-25T08:00:00' },
  ];
  const result = collapseByDay(trend);
  // 'a' = Mar 25, 'b' = empty string date (new group), 'c' = Mar 25 but after empty group = new group
  assert.equal(result.length, 3);
});

// ---------------------------------------------------------------------------
// collectDayDimensions
// ---------------------------------------------------------------------------

test('collectDayDimensions: collects all dims from all runs on the selected day', () => {
  const dims = collectDayDimensions(TREND, 'r3'); // Mar 24
  assert.equal(dims.size, 3); // maintainability, reliability, security
  assert.ok(dims.has('maintainability'));
  assert.ok(dims.has('reliability'));
  assert.ok(dims.has('security'));
});

test('collectDayDimensions: Mar 25 has maintainability + security', () => {
  const dims = collectDayDimensions(TREND, 'r1');
  assert.equal(dims.size, 2);
  assert.ok(dims.has('maintainability'));
  assert.ok(dims.has('security'));
});

test('collectDayDimensions: single-run day returns just that run dims', () => {
  const dims = collectDayDimensions(TREND, 'r5'); // Mar 23, only maintainability
  assert.equal(dims.size, 1);
  assert.ok(dims.has('maintainability'));
});

test('collectDayDimensions: unknown runId returns empty set', () => {
  const dims = collectDayDimensions(TREND, 'unknown');
  assert.equal(dims.size, 0);
});

test('collectDayDimensions: null/empty inputs return empty set', () => {
  assert.equal(collectDayDimensions(null, 'r1').size, 0);
  assert.equal(collectDayDimensions([], 'r1').size, 0);
  assert.equal(collectDayDimensions(TREND, null).size, 0);
});

test('collectDayDimensions: dimension names are lowercased', () => {
  const trend = [
    { runId: 'a', dateISO: '2026-01-01T00:00:00', dimensions: ['Maintainability', 'SECURITY'] },
  ];
  const dims = collectDayDimensions(trend, 'a');
  assert.ok(dims.has('maintainability'));
  assert.ok(dims.has('security'));
  assert.ok(!dims.has('Maintainability'));
});

// ---------------------------------------------------------------------------
// buildDailyRuns
// ---------------------------------------------------------------------------

test('buildDailyRuns: keeps first (newest) run per day', () => {
  const result = buildDailyRuns(AVAILABLE_RUNS, TREND);
  assert.equal(result.length, 3);
  assert.equal(result[0].runId, 'r1'); // Mar 25
  assert.equal(result[1].runId, 'r3'); // Mar 24
  assert.equal(result[2].runId, 'r5'); // Mar 23
});

test('buildDailyRuns: empty input returns empty', () => {
  assert.deepEqual(buildDailyRuns([], TREND), []);
  assert.deepEqual(buildDailyRuns(null, TREND), []);
});

test('buildDailyRuns: all runs on same day returns one entry', () => {
  const runs = [
    { runId: 'r1', dateLabel: 'Mar 25' },
    { runId: 'r2', dateLabel: 'Mar 25' },
  ];
  const trend = [
    { runId: 'r1', dateISO: '2026-03-25T14:00:00' },
    { runId: 'r2', dateISO: '2026-03-25T10:00:00' },
  ];
  const result = buildDailyRuns(runs, trend);
  assert.equal(result.length, 1);
  assert.equal(result[0].runId, 'r1');
});

// ---------------------------------------------------------------------------
// New test fixtures for day/week/month grouping
// ---------------------------------------------------------------------------

// Runs spanning 3 days / 3 ISO-weeks / 3 months (newest-first).
const MULTI = [
  { runId: 'm1', dateISO: '2026-05-02T12:00:00', dimensions: ['security'] },        // Sat W18, 2026-05
  { runId: 'm2', dateISO: '2026-04-14T18:00:00', dimensions: ['maintainability'] }, // Tue W16, 2026-04
  { runId: 'm3', dateISO: '2026-04-14T09:00:00', dimensions: ['reliability'] },     // Tue W16 (older same day)
  { runId: 'm4', dateISO: '2026-03-25T14:00:00', dimensions: ['security'] },        // Wed W13, 2026-03
  { runId: 'm5', dateISO: '2026-03-23T10:00:00', dimensions: ['performance'] },     // Mon W13, 2026-03
];

const MULTI_RUNS = [
  { runId: 'm1', dateLabel: '2 May 2026' },
  { runId: 'm2', dateLabel: '14 Apr 2026' },
  { runId: 'm3', dateLabel: '14 Apr 2026' },
  { runId: 'm4', dateLabel: '25 Mar 2026' },
  { runId: 'm5', dateLabel: '23 Mar 2026' },
];

// ---------------------------------------------------------------------------
// isoWeekKey
// ---------------------------------------------------------------------------

test('isoWeekKey: ISO week with Monday start', () => {
  assert.equal(isoWeekKey('2026-03-23T10:00:00'), '2026-W13'); // Monday
  assert.equal(isoWeekKey('2026-03-25T14:00:00'), '2026-W13'); // Wednesday same week
  assert.equal(isoWeekKey('2026-04-14T18:00:00'), '2026-W16');
  assert.equal(isoWeekKey('2026-01-05T00:00:00'), '2026-W02');
});

test('isoWeekKey: year-boundary week belongs to the ISO year of its Thursday', () => {
  assert.equal(isoWeekKey('2025-12-29T00:00:00'), '2026-W01'); // Mon whose Thu is 2026-01-01
  assert.equal(isoWeekKey('2026-01-01T00:00:00'), '2026-W01'); // Thursday
  assert.equal(isoWeekKey('2026-01-04T00:00:00'), '2026-W01'); // Sunday, still W01
});

test('isoWeekKey: missing/empty date returns empty string', () => {
  assert.equal(isoWeekKey(''), '');
  assert.equal(isoWeekKey(null), '');
});

// ---------------------------------------------------------------------------
// bucketKey
// ---------------------------------------------------------------------------

test('bucketKey: day/week/month keys', () => {
  assert.equal(bucketKey('2026-03-25T14:00:00', 'day'), '2026-03-25');
  assert.equal(bucketKey('2026-03-25T14:00:00', 'month'), '2026-03');
  assert.equal(bucketKey('2026-03-25T14:00:00', 'week'), '2026-W13');
  assert.equal(bucketKey('2026-03-25T14:00:00'), '2026-03-25'); // default day
  assert.equal(bucketKey('', 'week'), '');
});

// ---------------------------------------------------------------------------
// collapseByPeriod
// ---------------------------------------------------------------------------

test('collapseByPeriod: day matches collapseByDay (no-op parity)', () => {
  assert.deepEqual(collapseByPeriod(TREND, 'day'), collapseByDay(TREND));
});

test('collapseByPeriod: week keeps newest run per ISO week', () => {
  const result = collapseByPeriod(MULTI, 'week');
  assert.deepEqual(result.map((r) => r.runId), ['m1', 'm2', 'm4']);
});

test('collapseByPeriod: month keeps newest run per month', () => {
  const result = collapseByPeriod(MULTI, 'month');
  assert.deepEqual(result.map((r) => r.runId), ['m1', 'm2', 'm4']);
});

// ---------------------------------------------------------------------------
// collectPeriodDimensions
// ---------------------------------------------------------------------------

test('collectPeriodDimensions: month gathers all dims in the run\'s month', () => {
  const dims = collectPeriodDimensions(MULTI, 'm4', 'month'); // 2026-03: m4 + m5
  assert.equal(dims.size, 2);
  assert.ok(dims.has('security'));
  assert.ok(dims.has('performance'));
});

test('collectPeriodDimensions: week gathers all dims in the run\'s ISO week', () => {
  const dims = collectPeriodDimensions(MULTI, 'm2', 'week'); // W16: m2 + m3
  assert.equal(dims.size, 2);
  assert.ok(dims.has('maintainability'));
  assert.ok(dims.has('reliability'));
});

test('collectPeriodDimensions: day matches collectDayDimensions', () => {
  assert.deepEqual(
    [...collectPeriodDimensions(TREND, 'r3', 'day')].sort(),
    [...collectDayDimensions(TREND, 'r3')].sort(),
  );
});

// ---------------------------------------------------------------------------
// buildPeriodRuns
// ---------------------------------------------------------------------------

test('buildPeriodRuns: month keeps newest run per month', () => {
  const result = buildPeriodRuns(MULTI_RUNS, MULTI, 'month');
  assert.deepEqual(result.map((r) => r.runId), ['m1', 'm2', 'm4']);
});

test('buildPeriodRuns: day matches buildDailyRuns', () => {
  assert.deepEqual(buildPeriodRuns(AVAILABLE_RUNS, TREND, 'day'), buildDailyRuns(AVAILABLE_RUNS, TREND));
});
