import test from 'node:test';
import assert from 'node:assert/strict';
import {
  collapseByDay, collectDayDimensions, buildDailyRuns,
  bucketKey, isoWeekKey, collapseByPeriod, collectPeriodDimensions, buildPeriodRuns,
  extractDimensionPeriodSeries, sliceTrendAtRun,
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
// bucketKey: local-day semantics for UTC instants
// ---------------------------------------------------------------------------

/** The local calendar day the UI displays for an instant (what
 * formatShortDate/toLocaleDateString render), as YYYY-MM-DD. */
function displayedLocalDay(iso) {
  const d = new Date(iso);
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, '0'),
    String(d.getDate()).padStart(2, '0'),
  ].join('-');
}

test('bucketKey: UTC instants bucket by the LOCAL calendar day the UI displays', () => {
  // Backend dates are UTC instants ("...Z") while every user-facing date
  // renders local. Slicing the UTC date put a 00:30-local run in the
  // previous day's bucket: the row said 12 Jul, the grouping said 11 Jul.
  const iso = '2026-07-11T23:30:00Z';
  assert.equal(bucketKey(iso, 'day'), displayedLocalDay(iso));
});

test('bucketKey: month bucket follows the local day', () => {
  const iso = '2026-06-30T23:30:00Z';
  assert.equal(bucketKey(iso, 'month'), displayedLocalDay(iso).slice(0, 7));
});

test('bucketKey: week bucket follows the local day', () => {
  // 23:30Z on Sunday 2026-07-12 is already Monday (next ISO week) in any
  // timezone east of UTC+0:30.
  const iso = '2026-07-12T23:30:00Z';
  const localDay = displayedLocalDay(iso);
  const [y, m, d] = localDay.split('-').map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const isoYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(isoYear, 0, 1));
  const weekNo = Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
  const expected = `${isoYear}-W${String(weekNo).padStart(2, '0')}`;
  assert.equal(bucketKey(iso, 'week'), expected);
});

test('bucketKey: date-only strings pass through unchanged (no timezone context)', () => {
  assert.equal(bucketKey('2026-07-11', 'day'), '2026-07-11');
  assert.equal(bucketKey('2026-07-11', 'month'), '2026-07');
});

// ---------------------------------------------------------------------------
// in-progress runs never represent a bucket
// ---------------------------------------------------------------------------
// A running run's trend entry carries a PARTIAL cumulative average that
// moves as each dimension finishes. The Overview cards wait for the run to
// terminate; the chart, highlight union, and sparklines must do the same
// or they disagree with the cards mid-scan.

const TREND_WITH_RUNNING = [
  { runId: 'live', dateISO: '2026-03-25T16:00:00', status: 'in_progress', numericAverage: 5.1, dimensions: ['security'], dimensionDetails: [{ dimension: 'security', score: 5.1 }] },
  { runId: 'done2', dateISO: '2026-03-25T10:00:00', status: 'complete', numericAverage: 9.2, dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 9.2 }] },
  { runId: 'done1', dateISO: '2026-03-24T10:00:00', status: 'complete', numericAverage: 8.0, dimensions: ['security'], dimensionDetails: [{ dimension: 'security', score: 8.0 }] },
];

test('collapseByPeriod: an in-progress newest entry does not represent its bucket', () => {
  const result = collapseByPeriod(TREND_WITH_RUNNING, 'day');
  assert.equal(result.length, 2);
  assert.equal(result[0].runId, 'done2'); // Mar 25: terminal run wins, not "live"
  assert.equal(result[1].runId, 'done1');
});

test('collapseByPeriod: a bucket with only an in-progress entry is omitted', () => {
  const trend = [
    { runId: 'live', dateISO: '2026-03-26T09:00:00', status: 'in_progress', numericAverage: 4.0 },
    { runId: 'done1', dateISO: '2026-03-24T10:00:00', status: 'complete', numericAverage: 8.0 },
  ];
  const result = collapseByPeriod(trend, 'day');
  assert.equal(result.length, 1);
  assert.equal(result[0].runId, 'done1');
});

test('collectPeriodDimensions: an in-progress run does not contribute to the day union', () => {
  const dims = collectPeriodDimensions(TREND_WITH_RUNNING, 'done2', 'day');
  assert.ok(dims.has('maintainability'));
  assert.ok(!dims.has('security'), 'running run dims are not "analyzed" yet');
});

test('extractDimensionPeriodSeries: an in-progress entry never supplies a bucket point', () => {
  const series = extractDimensionPeriodSeries(TREND_WITH_RUNNING, 'security', 'day');
  // Mar 25's security only exists in the running run -> no Mar 25 point;
  // Mar 24's terminal 8.0 is the latest security point.
  assert.deepEqual(series.map((s) => s.runId), ['done1']);
});

test('entries without a status stay eligible (legacy payloads)', () => {
  const trend = [
    { runId: 'r1', dateISO: '2026-03-25T10:00:00', numericAverage: 9.0 },
  ];
  assert.equal(collapseByPeriod(trend, 'day').length, 1);
});

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

// ---------------------------------------------------------------------------
// extractDimensionPeriodSeries
// ---------------------------------------------------------------------------

// Newest-first, entries carry per-dimension scores.
const DIM_TREND = [
  { runId: 'd1', dateISO: '2026-05-02T12:00:00', dateLabel: '2 May',  overallGrade: 'Exemplary', dimensionDetails: [{ dimension: 'security', score: 9.0 }] },                                            // May, W18
  { runId: 'd2', dateISO: '2026-04-14T18:00:00', dateLabel: '14 Apr', overallGrade: 'Good',      dimensionDetails: [{ dimension: 'maintainability', score: 8.0, grade: 'Good' }] },                       // Apr, W16 (newest in week)
  { runId: 'd3', dateISO: '2026-04-13T09:00:00', dateLabel: '13 Apr', overallGrade: 'Good',      dimensionDetails: [{ dimension: 'maintainability', score: 7.0 }] },                                       // Apr, W16 (older same week)
  { runId: 'd4', dateISO: '2026-03-25T14:00:00', dateLabel: '25 Mar', overallGrade: 'Good',      dimensionDetails: [{ dimension: 'security', score: 6.0 }, { dimension: 'maintainability', score: 6.5 }] },// Mar, W13
  { runId: 'd5', dateISO: '2026-03-23T10:00:00', dateLabel: '23 Mar', overallGrade: 'Good',      dimensionDetails: [{ dimension: 'maintainability', score: 6.0 }] },                                       // Mar, W13 (older)
];

test('extractDimensionPeriodSeries: day keeps every run that scored the dim, oldest-first', () => {
  const s = extractDimensionPeriodSeries(DIM_TREND, 'maintainability', 'day');
  assert.deepEqual(s.map((x) => x.runId), ['d5', 'd4', 'd3', 'd2']);
  assert.deepEqual(s.map((x) => x.score), [6.0, 6.5, 7.0, 8.0]);
});

test('extractDimensionPeriodSeries: week collapses to newest-scored run per ISO week', () => {
  const s = extractDimensionPeriodSeries(DIM_TREND, 'maintainability', 'week');
  assert.deepEqual(s.map((x) => x.runId), ['d4', 'd2']); // W13->d4(6.5), W16->d2(8.0)
  assert.deepEqual(s.map((x) => x.score), [6.5, 8.0]);
});

test('extractDimensionPeriodSeries: month collapses to newest-scored run per month', () => {
  const s = extractDimensionPeriodSeries(DIM_TREND, 'maintainability', 'month');
  assert.deepEqual(s.map((x) => x.runId), ['d4', 'd2']); // Mar->d4, Apr->d2
});

test('extractDimensionPeriodSeries: within a bucket uses newest run that scored the dim, skipping runs that did not', () => {
  const trend = [
    { runId: 'a', dateISO: '2026-03-25T18:00:00', dimensionDetails: [{ dimension: 'security', score: 9 }] },        // newest in day, NO maintainability
    { runId: 'b', dateISO: '2026-03-25T09:00:00', dimensionDetails: [{ dimension: 'maintainability', score: 7 }] }, // older same day, HAS it
  ];
  const s = extractDimensionPeriodSeries(trend, 'maintainability', 'day');
  assert.equal(s.length, 1);
  assert.equal(s[0].runId, 'b');
  assert.equal(s[0].score, 7);
});

test('extractDimensionPeriodSeries: limit keeps the newest buckets', () => {
  const s = extractDimensionPeriodSeries(DIM_TREND, 'maintainability', 'day', 2);
  assert.deepEqual(s.map((x) => x.runId), ['d3', 'd2']); // newest two day-buckets, oldest-first
});

test('extractDimensionPeriodSeries: case-insensitive dimension match', () => {
  const s = extractDimensionPeriodSeries(DIM_TREND, 'Maintainability', 'day');
  assert.equal(s.length, 4);
});

test('extractDimensionPeriodSeries: carries dateISO/dateLabel/grade/overallGrade for the representative run', () => {
  const s = extractDimensionPeriodSeries(DIM_TREND, 'maintainability', 'day');
  const last = s[s.length - 1]; // d2
  assert.equal(last.dateISO, '2026-04-14T18:00:00');
  assert.equal(last.dateLabel, '14 Apr');
  assert.equal(last.grade, 'Good');
  assert.equal(last.overallGrade, 'Good');
});

test('extractDimensionPeriodSeries: runs with missing/invalid dateISO collapse into one bucket, newest scored kept', () => {
  // All falsy dates bucket to the empty key "", so these three runs form a
  // single bucket. e1 is newest but did not score maintainability (skipped
  // without consuming the bucket); e2 is the newest run that did; e3 is older.
  const trend = [
    { runId: 'e1', dateISO: null,      dimensionDetails: [{ dimension: 'security', score: 9 }] },
    { runId: 'e2', dateISO: '',        dimensionDetails: [{ dimension: 'maintainability', score: 8.0 }] },
    { runId: 'e3', dateISO: undefined, dimensionDetails: [{ dimension: 'maintainability', score: 4.0 }] },
  ];
  const s = extractDimensionPeriodSeries(trend, 'maintainability', 'day');
  assert.equal(s.length, 1);
  assert.equal(s[0].runId, 'e2');
  assert.equal(s[0].score, 8.0);
});

test('extractDimensionPeriodSeries: empty/invalid inputs return []', () => {
  assert.deepEqual(extractDimensionPeriodSeries([], 'maintainability', 'day'), []);
  assert.deepEqual(extractDimensionPeriodSeries(null, 'maintainability', 'day'), []);
  assert.deepEqual(extractDimensionPeriodSeries(DIM_TREND, '', 'day'), []);
});

// ---------------------------------------------------------------------------
// sliceTrendAtRun
// ---------------------------------------------------------------------------

test('sliceTrendAtRun: drops entries newer than the selected run, keeps it and older', () => {
  const sliced = sliceTrendAtRun(TREND, 'r3');
  assert.deepEqual(sliced.map((t) => t.runId), ['r3', 'r4', 'r5']);
});

test('sliceTrendAtRun: selecting the newest run returns the full trend', () => {
  assert.deepEqual(sliceTrendAtRun(TREND, 'r1').map((t) => t.runId), ['r1', 'r2', 'r3', 'r4', 'r5']);
});

test('sliceTrendAtRun: unknown or absent runId fails open to the full trend', () => {
  assert.equal(sliceTrendAtRun(TREND, 'nope').length, TREND.length);
  assert.equal(sliceTrendAtRun(TREND, null).length, TREND.length);
  assert.equal(sliceTrendAtRun(TREND, 'latest').length, TREND.length);
});

test('sliceTrendAtRun: empty/invalid trend returns []', () => {
  assert.deepEqual(sliceTrendAtRun([], 'r1'), []);
  assert.deepEqual(sliceTrendAtRun(null, 'r1'), []);
});
