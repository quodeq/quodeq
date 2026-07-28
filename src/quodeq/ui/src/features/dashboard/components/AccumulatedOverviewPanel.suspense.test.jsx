import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import { SidePaneProvider } from '../../side-pane/SidePaneProvider.jsx';

// Never resolves, so the lazy RunHistoryPanel stays suspended and the
// Suspense fallback (RunHistoryPanelPlaceholder) is what ends up on screen.
vi.mock('./RunHistoryPanel.jsx', () => new Promise(() => {}));

// Two days of trend data — enough for chartMountable (>= 2) to be true.
const TREND = [
  { runId: 't1', dateISO: '2026-07-03T10:00:00', dateLabel: 'Jul 3', numericAverage: 9, overallGrade: 'A', dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 9 }] },
  { runId: 't2', dateISO: '2026-06-15T10:00:00', dateLabel: 'Jun 15', numericAverage: 7, overallGrade: 'B', dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 7 }] },
];
const DIMS = [{ dimension: 'maintainability', overallScore: '7.0/10' }];

function baseData(trend) {
  return {
    accumulated: { summary: { numericAverage: 7 }, dimensions: DIMS },
    accumulatedDimensions: DIMS,
    availableRuns: [],
    dailyRuns: null,
    overviewRunIndex: 0,
    trend,
    selectedRunId: 't1',
    granularity: 'day',
    projectInfo: null,
    selectedProject: 'proj1',
    selectedSource: 'local',
  };
}

const callbacks = {
  onRunClick: vi.fn(),
  onDimensionClick: vi.fn(),
  onNavigate: vi.fn(),
};

describe('AccumulatedOverviewPanel — chart Suspense fallback', () => {
  it('renders the panel-shell placeholder while the chart chunk is unresolved (chartMountable)', async () => {
    render(
      <SidePaneProvider>
        <AccumulatedOverviewPanel data={baseData(TREND)} callbacks={callbacks} />
      </SidePaneProvider>,
    );
    expect(await screen.findByTestId('run-history-panel-placeholder')).toBeInTheDocument();
  });

  it('keeps the chartMountable gate: renders nothing (not even the placeholder) with < 2 days of trend', () => {
    render(
      <SidePaneProvider>
        <AccumulatedOverviewPanel data={baseData([TREND[0]])} callbacks={callbacks} />
      </SidePaneProvider>,
    );
    expect(screen.queryByTestId('run-history-panel-placeholder')).toBeNull();
  });
});
