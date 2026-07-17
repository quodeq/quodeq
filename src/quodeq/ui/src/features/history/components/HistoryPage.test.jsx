import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HistoryPage from './HistoryPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

// The chart panel is lazy-loaded and pulls in recharts; stub it so these
// tests exercise only the table (the part with the delete-button gating).
vi.mock('./HistoryChartPanel.jsx', () => ({
  default: () => null,
}));

// Shared-repo runs have no delete route on the backend (mutation is
// local-only by design, same as dismiss/restore/verify). HistoryPage must
// only wire onDeleteRun into the table when selectedSource is 'local' —
// HistoryRow already gates its delete button on `{onDelete && ...}`, so
// passing undefined is what makes the button vanish for shared.
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

function makeFakeApi(overrides = {}) {
  return {
    deleteEvaluation: vi.fn(async () => ({ ok: true })),
    getDashboard: vi.fn(async () => ({})),
    sharedGetDashboard: vi.fn(async () => ({})),
    getProjectScores: vi.fn(async () => ({})),
    sharedGetProjectScores: vi.fn(async () => ({})),
    ...overrides,
  };
}

function renderHistoryPage(selectedSource, overrides = {}) {
  const QC = withQueryClient();
  const fakeApi = makeFakeApi();
  render(
    <QC>
      <ApiProvider value={fakeApi}>
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
          selectedSource={selectedSource}
          loading={false}
          isFetching={false}
          {...overrides}
        />
      </ApiProvider>
    </QC>,
  );
  return fakeApi;
}

describe('HistoryPage — delete-run source gating', () => {
  it('shows the delete button on a row when source is local', () => {
    renderHistoryPage('local');
    // The delete button lives inside an aria-hidden chevron column (a
    // pre-existing decorative wrapper), so it must be queried with
    // hidden:true rather than treated as a real accessibility-tree gap.
    expect(screen.getByRole('button', { name: 'Delete run', hidden: true })).toBeInTheDocument();
  });

  it('hides the delete button on every row when source is shared', () => {
    renderHistoryPage('shared');
    expect(screen.queryByRole('button', { name: 'Delete run', hidden: true })).toBeNull();
    // The row itself (and its chevron) must still render — only the delete
    // affordance is gone.
    expect(screen.getByText('Jul 1, 2026')).toBeInTheDocument();
  });
});
