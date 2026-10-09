import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dimensionPeriodDeltas } from './dimensionPeriodDeltas.js';

const row = (runId, dateISO, score, critical, majors, extra = {}) => ({
  runId, dateISO, dateLabel: dateISO.slice(0, 10), status: 'completed',
  dimensionDetails: [{ dimension: 'Security', score, critical, majors }, { dimension: 'usability', score: 5, critical: 9, majors: 9 }],
  ...extra,
});

// Newest first, like the trend payload. Two runs in the week of 23 March,
// one the week before, one in February.
const TREND = [
  row('r4', '2026-03-26T10:00:00', 8.0, 1, 4),
  row('r3', '2026-03-24T10:00:00', 7.5, 2, 5),
  row('r2', '2026-03-18T10:00:00', 7.0, 3, 9),
  row('r1', '2026-02-10T10:00:00', 6.0, 0, 2),
];

test('day: the newest day against the day before, criticals taken out of the majors', () => {
  assert.deepEqual(dimensionPeriodDeltas(TREND, 'security', 'day', null), {
    score: 0.5, chips: { critical: -1, major: 0 },
  });
});

test('week: the newest run of each week, so the two runs of one week collapse', () => {
  assert.deepEqual(dimensionPeriodDeltas(TREND, 'security', 'week', null), {
    score: 1.0, chips: { critical: -2, major: -3 },
  });
});

test('month: compares with the month before', () => {
  assert.deepEqual(dimensionPeriodDeltas(TREND, 'security', 'month', null), {
    score: 2.0, chips: { critical: 1, major: 1 },
  });
});

test('the run on show cuts the trend: an earlier run compares with what came before it', () => {
  assert.deepEqual(dimensionPeriodDeltas(TREND, 'security', 'day', 'r3'), {
    score: 0.5, chips: { critical: -1, major: -3 },
  });
});

test('a period the dimension skipped is passed over, like the Overview cards', () => {
  const trend = [
    { runId: 'x', dateISO: '2026-03-27T10:00:00', status: 'completed', dimensionDetails: [{ dimension: 'usability', score: 5, critical: 0, majors: 0 }] },
    ...TREND,
  ];
  assert.deepEqual(dimensionPeriodDeltas(trend, 'security', 'day', null), {
    score: 0.5, chips: { critical: -1, major: 0 },
  });
});

test('no previous period: nothing to compare', () => {
  assert.deepEqual(dimensionPeriodDeltas(TREND.slice(3), 'security', 'day', null), { score: null, chips: null });
  assert.deepEqual(dimensionPeriodDeltas([], 'security', 'day', null), { score: null, chips: null });
  assert.deepEqual(dimensionPeriodDeltas(TREND, 'reliability', 'day', null), { score: null, chips: null });
});

test('a row without counts still moves the score but not the chips', () => {
  const trend = [row('n', '2026-03-28T10:00:00', 9.0, undefined, undefined), ...TREND];
  assert.deepEqual(dimensionPeriodDeltas(trend, 'security', 'day', null), { score: 1.0, chips: null });
});
