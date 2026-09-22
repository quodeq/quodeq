import test from 'node:test';
import assert from 'node:assert/strict';
import { bucketKey, isoWeekKey, collapseByPeriod, collectPeriodDimensions, extractDimensionPeriodSeries } from './dailyGrouping.js';
import { TREND_WITH_RUNNING, displayedLocalDay } from './_dailyGrouping.fixtures.js';

/**
 * Split from dailyGrouping.test.js: bucketKey/isoWeekKey local-day
 * semantics, and the in-progress-run-never-represents-a-bucket guard.
 */

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

test('isoWeekKey: impossible calendar components are rejected, not normalized', () => {
  // Date.UTC would normalize 2026-02-31 to 2026-03-03; the entry must not
  // be grouped under a week it never specified.
  assert.equal(isoWeekKey('2026-02-31'), '');
  assert.equal(isoWeekKey('2026-13-01'), '');
  // A valid edge day (leap day) still produces a week key.
  assert.notEqual(isoWeekKey('2028-02-29'), '');
});

test('isoWeekKey: missing/empty date returns empty string', () => {
  assert.equal(isoWeekKey(''), '');
  assert.equal(isoWeekKey(null), '');
});

test('bucketKey: day/week/month keys', () => {
  assert.equal(bucketKey('2026-03-25T14:00:00', 'day'), '2026-03-25');
  assert.equal(bucketKey('2026-03-25T14:00:00', 'month'), '2026-03');
  assert.equal(bucketKey('2026-03-25T14:00:00', 'week'), '2026-W13');
  assert.equal(bucketKey('2026-03-25T14:00:00'), '2026-03-25'); // default day
  assert.equal(bucketKey('', 'week'), '');
});
