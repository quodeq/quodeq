import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAccumulatedComputations } from './AccumulatedOverviewPanel.jsx';

// Newest-first, one run per day, maintainability scored in every run.
const TREND = [
  { runId: 't1', dateISO: '2026-07-03T10:00:00', dateLabel: 'Jul 3', numericAverage: 9, overallGrade: 'A', dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 9 }] },
  { runId: 't2', dateISO: '2026-06-15T10:00:00', dateLabel: 'Jun 15', numericAverage: 7, overallGrade: 'B', dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 7 }] },
  { runId: 't3', dateISO: '2026-05-10T10:00:00', dateLabel: 'May 10', numericAverage: 4, overallGrade: 'D', dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 4 }] },
];

const DIMS = [{ dimension: 'maintainability', overallScore: '7.0/10' }];

function runHook(selectedRunId) {
  return renderHook(() => useAccumulatedComputations({
    accumulated: { summary: { numericAverage: 7 }, dimensions: DIMS },
    accumulatedDimensions: DIMS,
    availableRuns: [],
    dailyRuns: null,
    overviewRunIndex: 0,
    trend: TREND,
    selectedRunId,
    granularity: 'day',
  })).result.current;
}

describe('useAccumulatedComputations dimTrends (as-of)', () => {
  it('uses the full series at the latest run', () => {
    const { dimTrends } = runHook('t1');
    expect(dimTrends.maintainability.scores).toEqual([4, 7, 9]);
    expect(dimTrends.maintainability.delta).toBe(2);
  });

  it('truncates the series at the selected previous run so arrows match as-of scores', () => {
    const { dimTrends } = runHook('t2');
    // Entries newer than t2 are gone: the sparkline ends at the selected
    // period and the delta compares t2 vs t3 (7 - 4), not t1 vs t2.
    expect(dimTrends.maintainability.scores).toEqual([4, 7]);
    expect(dimTrends.maintainability.delta).toBe(3);
  });
});
