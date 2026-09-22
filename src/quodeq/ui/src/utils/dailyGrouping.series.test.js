import test from 'node:test';
import assert from 'node:assert/strict';
import { extractDimensionPeriodSeries, sliceTrendAtRun } from './dailyGrouping.js';
import { TREND, DIM_TREND } from './_dailyGrouping.fixtures.js';

/**
 * Split from dailyGrouping.test.js: extractDimensionPeriodSeries and
 * sliceTrendAtRun.
 */

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
