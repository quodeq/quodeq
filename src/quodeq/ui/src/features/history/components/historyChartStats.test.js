import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildHistoryChartRows } from './historyChartStats.js';

const row = (runId, score, majors, openTypes) => ({ runId, dateISO: `2026-09-0${runId.slice(1)}`, dateLabel: runId, runNumericAverage: score, dimensionDetails: [{ critical: 0, majors, openTypes }] });

test('buildHistoryChartRows plots oldest first with the run score and its counts', () => {
  const rows = buildHistoryChartRows([row('r3', '9.0', 1, 30), row('r2', '8.5', 3, 33), row('r1', '8.0', 5, 40)], 'r2', 40);
  assert.deepEqual(rows.map((r) => [r.runId, r.numericAverage, r.critical, r.majors, r.openTypes]), [['r1', 8, 0, 5, 40], ['r2', 8.5, 0, 3, 33], ['r3', 9, 0, 1, 30]]);
});

test('buildHistoryChartRows windows around the selected run', () => {
  const trend = Array.from({ length: 10 }, (_, i) => row(`r${9 - i}`, '8.0', 1, 1));
  const rows = buildHistoryChartRows(trend, 'r0', 4);
  assert.equal(rows.length, 4);
  assert.ok(rows.some((r) => r.runId === 'r0'));
});
