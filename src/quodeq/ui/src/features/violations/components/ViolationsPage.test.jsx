import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ViolationsPage, { ViolationsSubTabContent } from './ViolationsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

// Shared projects have no mutation route on the backend (dismiss/restore/
// delete are local-only by design, and the same project id can exist in both
// worlds). ViolationsSubTabContent is the App-adjacent wiring point between
// useDismissedFindings' handlers and DismissedSubTab's action buttons: when
// selectedSource is 'shared' it must pass undefined instead of the real
// handlers so the buttons vanish while the dismissed list stays visible.
const sampleA = { req: 'A1', file: 'a.py', line: 10, severity: 'minor', principle: 'P1' };
const sampleB = { req: 'B1', file: 'b.py', line: 20, severity: 'major', principle: 'P2' };

function renderDismissedSubTab(selectedSource, overrides = {}) {
  const handlers = {
    handleRestore: vi.fn(),
    handleRestoreAll: vi.fn(),
    handleDelete: vi.fn(),
    handleDeleteAll: vi.fn(),
    ...overrides,
  };
  render(
    <ViolationsSubTabContent
      activeSubTab="dismissed"
      dismissed={[sampleA, sampleB]}
      visibleDimensions={[]}
      callbacks={{}}
      fileCurrentPath=""
      setFileCurrentPath={() => {}}
      selectedSource={selectedSource}
      {...handlers}
    />
  );
  return handlers;
}

describe('ViolationsSubTabContent — dismissed sub-tab, source gating', () => {
  it('shows Restore/Delete and Restore all/Delete all when source is local', () => {
    renderDismissedSubTab('local');
    expect(screen.getAllByRole('button', { name: 'Restore' })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Restore all' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete all' })).toBeInTheDocument();
  });

  it('hides every action button when source is shared, but keeps the list visible', () => {
    renderDismissedSubTab('shared');
    expect(screen.queryByRole('button', { name: 'Restore' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Restore all' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete all' })).toBeNull();
    expect(screen.getByText('a.py:10')).toBeInTheDocument();
    expect(screen.getByText('b.py:20')).toBeInTheDocument();
  });

  it('renders the empty message instead of DismissedSubTab when there are no dismissed findings', () => {
    render(
      <ViolationsSubTabContent
        activeSubTab="dismissed"
        dismissed={[]}
        visibleDimensions={[]}
        callbacks={{}}
        fileCurrentPath=""
        setFileCurrentPath={() => {}}
        selectedSource="shared"
        handleRestore={vi.fn()}
        handleRestoreAll={vi.fn()}
        handleDelete={vi.fn()}
        handleDeleteAll={vi.fn()}
      />
    );
    expect(screen.getByText('No dismissed violations.')).toBeInTheDocument();
  });
});

// Final whole-branch review: Critical 1 (evaluate CTA gating), Finding 3
// (teammate persona -- shared selection + zero local projects), Finding 6
// (shared read-only chip). ViolationsPage's default export needs a
// QueryClientProvider (useDismissedFindings calls useQueryClient()).
function baseData(overrides = {}) {
  return {
    accumulatedDimensions: [],
    selectedProject: 'shared-1',
    projects: [],
    projectsLoaded: true,
    projectName: 'Shared Repo',
    loading: false,
    isFetching: false,
    dismissRefreshKey: 0,
    selectedSource: 'shared',
    ...overrides,
  };
}

function renderPage(data, callbacks = {}) {
  const QC = withQueryClient();
  return render(
    <QC>
      <ViolationsPage data={data} callbacks={callbacks} />
    </QC>
  );
}

describe('ViolationsPage — evaluate CTA gating for shared (Critical 1)', () => {
  it('shared source, no evaluations yet: no Start evaluation CTA, shared-specific copy', () => {
    renderPage(baseData());
    expect(screen.getByText('No completed evaluation yet')).toBeInTheDocument();
    expect(screen.getByText('no completed evaluation in this remote project yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start evaluation' })).toBeNull();
  });

  it('local source, no evaluations yet: Start evaluation CTA present (existing behavior)', () => {
    renderPage(baseData({
      selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }],
    }));
    expect(screen.getByRole('button', { name: 'Start evaluation' })).toBeInTheDocument();
  });
});

describe('ViolationsPage — teammate persona: shared selection + zero local projects (Finding 3)', () => {
  it('shared source with an empty LOCAL projects list renders the shared content path, not the Add-a-project wall', () => {
    renderPage(baseData({
      accumulatedDimensions: [{ dimension: 'security', violations: [], compliance: [] }],
    }));
    expect(screen.queryByText('No projects yet')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a project' })).toBeNull();
  });

  it('local source with an empty local projects list still shows the Add-a-project wall (unchanged)', () => {
    renderPage(baseData({ selectedSource: 'local', selectedProject: '', projects: [] }));
    expect(screen.getByText('No projects yet')).toBeInTheDocument();
  });
});

// Item 1 regression: ViolationsPage fires its mount effect (onRefresh) on
// EVERY mount, including plain drill-down/back navigation with no mutation
// -- the page remounts on every round trip through a file/principle detail.
// A prior revision wired the route's onRefresh to the ACTIVE
// scheduleDashboardReconcile, turning routine navigation into a forced
// refetch of the 10-20 MB dashboard payload (the freeze refetchType:'none'
// exists to avoid). The mount effect must only ever reach onRefresh -- never
// onReconcile, which is reserved for the Dismissed sub-tab's mutation
// handlers (see useDismissedFindings.js).
describe('ViolationsPage — mount-effect onRefresh does not reach onReconcile (Item 1 regression)', () => {
  it('calls onRefresh on mount but never onReconcile, even though both are supplied', () => {
    const onRefresh = vi.fn();
    const onReconcile = vi.fn();
    renderPage(
      baseData({ selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }] }),
      { onRefresh, onReconcile },
    );
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onReconcile).not.toHaveBeenCalled();
  });
});

describe('ViolationsPage — scenario 9: loader gate, containment, refresh dim', () => {
  it('background refetch over an empty project keeps the empty state, no loader', () => {
    const { container } = renderPage(baseData({ loading: false, isFetching: true }));
    expect(container.querySelector('.loading-screen')).toBeNull();
    expect(screen.getByText('No completed evaluation yet')).toBeInTheDocument();
  });

  it('initial load renders exactly one inline loader inside the page frame', () => {
    const { container } = renderPage(baseData({ loading: true, isFetching: true }));
    expect(container.querySelectorAll('.loading-screen').length).toBe(1);
    const loader = container.querySelector('.loading-screen--inline');
    expect(loader).not.toBeNull();
    const frame = container.querySelector('.violations-page--terminal');
    expect(frame).not.toBeNull();
    expect(frame.contains(loader)).toBe(true);
  });

  it('applies the refresh dim class to the empty state during a background refetch', () => {
    const { container } = renderPage(baseData({ loading: false, isFetching: true }));
    expect(container.querySelector('.violations-page--terminal').className).toContain('dashboard-refreshing');
  });

  it('applies the refresh dim class to real content during a background refetch', () => {
    const { container } = renderPage(baseData({
      accumulatedDimensions: [{ dimension: 'security', violations: [], compliance: [] }],
      loading: false, isFetching: true,
    }));
    expect(container.querySelector('.violations-page--terminal').className).toContain('dashboard-refreshing');
  });
});

describe('ViolationsPage — error state + retry feedback (P4-T2)', () => {
  it('error + no data renders the framed error state with a working Retry', () => {
    const onRetry = vi.fn();
    renderPage(
      baseData({ selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }], error: 'Failed to load' }),
      { onRetry },
    );
    expect(screen.getByText("Couldn't load this project")).toBeInTheDocument();
    fireEvent.click(screen.getByText('Retry'));
    expect(onRetry).toHaveBeenCalled();
  });

  it('error + isFetching renders the inline loader instead of the error state', () => {
    const { container } = renderPage(
      baseData({ selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }], error: 'Failed to load', isFetching: true }),
    );
    expect(screen.queryByText("Couldn't load this project")).toBeNull();
    expect(container.querySelector('.loading-screen')).toBeTruthy();
  });

  it('data present with a stale error still renders the data, not the error screen', () => {
    renderPage(baseData({
      selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }],
      accumulatedDimensions: [{ dimension: 'security', violations: [], compliance: [] }],
      error: 'Failed to load',
    }));
    expect(screen.queryByText("Couldn't load this project")).toBeNull();
  });
});

describe('ViolationsPage — shared read-only chip (Finding 6)', () => {
  it('shows the chip for a shared project with data', () => {
    renderPage(baseData({
      accumulatedDimensions: [{ dimension: 'security', violations: [], compliance: [] }],
    }));
    expect(screen.getByText('remote · read-only')).toBeInTheDocument();
  });

  it('omits the chip for a local project', () => {
    renderPage(baseData({
      selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }],
      accumulatedDimensions: [{ dimension: 'security', violations: [], compliance: [] }],
    }));
    expect(screen.queryByText('remote · read-only')).toBeNull();
  });
});
