import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HistoryPage from './HistoryPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

// The lazy-loaded chart panel used to have no error boundary around its
// Suspense: a chunk-load failure (offline, deploy skew) used to crash the
// whole History page. It must now fall back to an inline error instead.
vi.mock('./HistoryChartPanel.jsx', () => { throw new Error('chunk load failed'); });

vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({ showToast: vi.fn() }),
}));

const trend = [
  {
    runId: 'r1',
    status: 'done',
    dateISO: '2026-07-01T10:00:00Z',
    dateLabel: '1 Jul 2026',
    numericAverage: 8.2,
    overallGrade: 'B',
    dimensionDetails: [{ dimension: 'security', score: 8.2 }],
  },
];
const availableRuns = [
  { runId: 'r1', status: 'done', dateISO: '2026-07-01T10:00:00Z', dateLabel: '1 Jul 2026' },
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

describe('HistoryPage — chart error boundary', () => {
  it('renders a fallback instead of crashing when the chart chunk fails to load', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
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

    expect(await screen.findByText('The chart could not be displayed.')).toBeInTheDocument();
    // The rest of the page (evaluations table) must still be usable.
    expect(screen.queryByTestId('history-chart-panel-placeholder')).not.toBeInTheDocument();
  });
});
