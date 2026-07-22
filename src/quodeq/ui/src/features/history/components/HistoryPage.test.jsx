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

// Final whole-branch review: Critical 1 (evaluate CTA gating), Finding 3
// (teammate persona -- shared selection + zero local projects), Finding 6
// (shared read-only chip).
function renderHistoryPageWithData(overrides = {}) {
  const QC = withQueryClient();
  const fakeApi = makeFakeApi();
  render(
    <QC>
      <ApiProvider value={fakeApi}>
        <HistoryPage
          trend={[]}
          selection={{ selectedRunId: null }}
          availableRuns={[]}
          dimensions={{}}
          callbacks={{
            onRunClick: vi.fn(),
            onDimensionClick: vi.fn(),
            onNavigate: vi.fn(),
            onRunChange: vi.fn(),
            onRunDeleted: vi.fn(),
          }}
          projectInfo={null}
          projects={[]}
          projectsLoaded
          selectedProject="shared-1"
          selectedSource="shared"
          loading={false}
          isFetching={false}
          {...overrides}
        />
      </ApiProvider>
    </QC>,
  );
  return fakeApi;
}

describe('HistoryPage — evaluate CTA gating for shared (Critical 1)', () => {
  it('shared source, no evaluations yet: no Start evaluation CTA, shared-specific copy', () => {
    renderHistoryPageWithData();
    expect(screen.getByText('No completed evaluation yet')).toBeInTheDocument();
    expect(screen.getByText('no completed evaluation in this remote project yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start evaluation' })).toBeNull();
  });

  it('local source, no evaluations yet: Start evaluation CTA present (existing behavior)', () => {
    renderHistoryPageWithData({
      selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }],
    });
    expect(screen.getByRole('button', { name: 'Start evaluation' })).toBeInTheDocument();
  });
});

describe('HistoryPage — teammate persona: shared selection + zero local projects (Finding 3)', () => {
  it('shared source with an empty LOCAL projects list renders the shared content path, not the Add-a-project wall', () => {
    renderHistoryPageWithData({ trend, availableRuns, selection: { selectedRunId: 'r1' } });
    expect(screen.queryByText('No projects yet')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a project' })).toBeNull();
  });

  it('local source with an empty local projects list still shows the Add-a-project wall (unchanged)', () => {
    renderHistoryPageWithData({ selectedSource: 'local', selectedProject: '', projects: [] });
    expect(screen.getByText('No projects yet')).toBeInTheDocument();
  });
});

describe('HistoryPage — shared read-only chip (Finding 6)', () => {
  it('shows the chip for a shared project with data', () => {
    renderHistoryPageWithData({ trend, availableRuns, selection: { selectedRunId: 'r1' } });
    expect(screen.getByText('remote · read-only')).toBeInTheDocument();
  });

  it('omits the chip for a local project', () => {
    renderHistoryPageWithData({
      trend, availableRuns, selection: { selectedRunId: 'r1' },
      selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }],
    });
    expect(screen.queryByText('remote · read-only')).toBeNull();
  });
});
