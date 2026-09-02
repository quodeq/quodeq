import test from 'node:test';
import assert from 'node:assert/strict';
import {
  collapseByDay, collectDayDimensions, buildDailyRuns,
  collapseByPeriod, collectPeriodDimensions, buildPeriodRuns,
} from './dailyGrouping.js';
import { TREND, AVAILABLE_RUNS, MULTI, MULTI_RUNS } from './_dailyGrouping.fixtures.js';

/**
 * Split from dailyGrouping.test.js: collapseByDay/Period,
 * collectDayDimensions/PeriodDimensions, buildDailyRuns/PeriodRuns.
 */

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

test('buildPeriodRuns: month keeps newest run per month', () => {
  const result = buildPeriodRuns(MULTI_RUNS, MULTI, 'month');
  assert.deepEqual(result.map((r) => r.runId), ['m1', 'm2', 'm4']);
});

test('buildPeriodRuns: day matches buildDailyRuns', () => {
  assert.deepEqual(buildPeriodRuns(AVAILABLE_RUNS, TREND, 'day'), buildDailyRuns(AVAILABLE_RUNS, TREND));
});
