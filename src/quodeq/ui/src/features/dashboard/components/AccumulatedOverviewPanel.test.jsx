import { describe, it, expect } from 'vitest';
import { renderHook, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useAccumulatedComputations, AccumulatedHeroSection } from './AccumulatedOverviewPanel.jsx';

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

describe('useAccumulatedComputations selectedDayDimNames (multi-run day)', () => {
  // Two runs on the SAME day evaluating different dimensions, plus an older
  // day. The day-highlight must union the whole day, not just the newest
  // run (v1.6.0 bug report: only the last evaluation's cards lit up).
  const MULTI_RUN_DAY_TREND = [
    { runId: 'm1', dateISO: '2026-07-12T14:00:00', dateLabel: 'Jul 12', numericAverage: 9, overallGrade: 'A', dimensions: ['security'], dimensionDetails: [{ dimension: 'security', score: 9 }] },
    { runId: 'm2', dateISO: '2026-07-12T09:00:00', dateLabel: 'Jul 12', numericAverage: 8, overallGrade: 'B', dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 8 }] },
    { runId: 'm3', dateISO: '2026-07-10T10:00:00', dateLabel: 'Jul 10', numericAverage: 6, overallGrade: 'C', dimensions: ['reliability'], dimensionDetails: [{ dimension: 'reliability', score: 6 }] },
  ];

  it('unions dimensions across every run of the selected day', () => {
    const { selectedDayDimNames } = renderHook(() => useAccumulatedComputations({
      accumulated: { summary: { numericAverage: 8 }, dimensions: DIMS },
      accumulatedDimensions: DIMS,
      availableRuns: [],
      dailyRuns: null,
      overviewRunIndex: 0,
      trend: MULTI_RUN_DAY_TREND,
      selectedRunId: 'm1',
      granularity: 'day',
    })).result.current;
    expect(selectedDayDimNames.has('security')).toBe(true);
    expect(selectedDayDimNames.has('maintainability')).toBe(true);
    expect(selectedDayDimNames.has('reliability')).toBe(false);
  });
});

// Task 19 — the Overview page header shows a "remote · read-only" chip
// (+ publisher sub line where available) for shared projects, and nothing
// extra for local ones.
describe('AccumulatedHeroSection shared read-only chip', () => {
  const baseProps = {
    accumulated: { summary: { numericAverage: 7 } },
    scoreDelta: null,
    lastDate: null,
    accumulatedDimensions: [],
    projectName: 'proj1',
    projectInfo: null,
    onCardNavigate: undefined,
  };

  it('shows the chip for a shared project', () => {
    render(<AccumulatedHeroSection {...baseProps} selectedSource="shared" />);
    expect(screen.getByText('remote · read-only')).toBeInTheDocument();
  });

  it('omits the chip for a local project', () => {
    render(<AccumulatedHeroSection {...baseProps} selectedSource="local" />);
    expect(screen.queryByText('remote · read-only')).toBeNull();
  });

  it('shows the publisher sub line when projectInfo.publishedBy is available', () => {
    render(<AccumulatedHeroSection {...baseProps} selectedSource="shared" projectInfo={{ publishedBy: 'alice' }} />);
    expect(screen.getByText('published by alice')).toBeInTheDocument();
  });
});
