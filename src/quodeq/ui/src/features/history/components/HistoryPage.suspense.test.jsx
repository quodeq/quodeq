import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HistoryPage from './HistoryPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

// Never resolves, so the lazy HistoryChartPanel stays suspended and the
// Suspense fallback (HistoryChartPanelPlaceholder) is what ends up on screen.
vi.mock('./HistoryChartPanel.jsx', () => new Promise(() => {}));

const trend = [
  {
    runId: 'r1',
    status: 'complete',
    dateISO: '2026-07-01T10:00:00Z',
    dateLabel: '1 Jul 2026',
    numericAverage: 8.2,
    overallGrade: 'B',
    dimensionDetails: [{ dimension: 'security', score: 8.2 }],
  },
];
const availableRuns = [
  { runId: 'r1', status: 'complete', dateISO: '2026-07-01T10:00:00Z', dateLabel: '1 Jul 2026' },
];

function makeFakeApi() {
  return {
    deleteEvaluation: vi.fn(async () => ({ ok: true })),
    getDashboard: vi.fn(async () => ({})),
    sharedGetDashboard: vi.fn(async () => ({})),
    getProjectScores: vi.fn(async () => ({})),
    sharedGetProjectScores: vi.fn(async () => ({})),
  };
}

describe('HistoryPage — chart Suspense fallback', () => {
  it('renders the fixed-height placeholder while the chart chunk is unresolved', async () => {
    const QC = withQueryClient();
    render(
      <QC>
        <ApiProvider value={makeFakeApi()}>
          <HistoryPage
            trend={trend}
            selection={{ selectedRunId: 'r1' }}
            availableRuns={availableRuns}
            dimensions={{}}
            callbacks={{
              onRunClick: vi.fn(),
              onDimensionClick: vi.fn(),
              onNavigate: vi.fn(),
              onRunChange: vi.fn(),
              onRunDeleted: vi.fn(),
            }}
            projectInfo={{ displayName: 'Test Project' }}
            projects={[{ id: 'proj1', name: 'proj1' }]}
            projectsLoaded
            selectedProject="proj1"
            selectedSource="local"
            loading={false}
            isFetching={false}
          />
        </ApiProvider>
      </QC>,
    );

    expect(await screen.findByTestId('history-chart-panel-placeholder')).toBeInTheDocument();
  });
});
