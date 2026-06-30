import test from 'node:test';
import assert from 'node:assert/strict';
import { filterTrendByVisibleStandardsDaily } from './scoreFiltering.js';
import { collapseByPeriod } from './dailyGrouping.js';

// Newest-first. The March bucket's NEWEST run (a3, Mar 28) measured only a
// HIDDEN standard (performance); an earlier March run (a2, Mar 25) measured
// the visible one (security). This is where day-keying and period-keying
// diverge: keying the accumulated-average map by day drops the March bucket
// (a3's day has no visible eval), while keying by month keeps it with a2's
// accumulated average. When every run measures a visible standard the two
// behave identically — so this hidden-standard run is what makes the red
// step real.
const TREND = [
  { runId: 'a4', dateISO: '2026-04-14T18:00:00', dimensions: ['security'],
    dimensionDetails: [{ dimension: 'security', score: 8 }] },
  { runId: 'a3', dateISO: '2026-03-28T09:00:00', dimensions: ['performance'],
    dimensionDetails: [{ dimension: 'performance', score: 2 }] }, // hidden standard
  { runId: 'a2', dateISO: '2026-03-25T14:00:00', dimensions: ['security'],
    dimensionDetails: [{ dimension: 'security', score: 6 }] },
  { runId: 'a1', dateISO: '2026-03-23T10:00:00', dimensions: ['security'],
    dimensionDetails: [{ dimension: 'security', score: 4 }] },
];
const VISIBLE = new Set(['security']);

test('month granularity: keeps a bucket whose newest run measured only hidden standards', () => {
  const periodTrend = collapseByPeriod(TREND, 'month'); // [a4 (Apr), a3 (Mar, newest)]
  const result = filterTrendByVisibleStandardsDaily(TREND, periodTrend, VISIBLE, 'month');
  assert.equal(result.length, 2); // both April and March kept
  assert.equal(result[0].runId, 'a4');
  assert.equal(result[0].numericAverage, 8);
  assert.equal(result[1].runId, 'a3'); // March bucket survives (day-keying would drop it)
  assert.equal(result[1].numericAverage, 6); // accumulated avg as of the last VISIBLE March run (a2)
});

test('day granularity (3-arg legacy call) is unchanged: one entry per visible day', () => {
  const dayTrend = collapseByPeriod(TREND, 'day');
  const result = filterTrendByVisibleStandardsDaily(TREND, dayTrend, VISIBLE); // no granularity arg
  // a3's day (Mar 28) has no visible eval, so it's dropped at day granularity — unchanged behavior.
  assert.deepEqual(result.map((r) => r.runId), ['a4', 'a2', 'a1']);
});
