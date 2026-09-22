import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useState } from 'react';
import ViolationsPage from './ViolationsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

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

  it('initial load renders the violations skeleton inside the page frame, no spinner', () => {
    const { container } = renderPage(baseData({ loading: true, isFetching: true }));
    expect(container.querySelector('.loading-screen')).toBeNull();
    const skeleton = container.querySelector('.violations-skeleton');
    expect(skeleton).not.toBeNull();
    const frame = container.querySelector('.violations-page--terminal');
    expect(frame).not.toBeNull();
    expect(frame.contains(skeleton)).toBe(true);
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

  it('error + isFetching renders the skeleton instead of the error state', () => {
    const { container } = renderPage(
      baseData({ selectedSource: 'local', selectedProject: 'p1', projects: [{ id: 'p1', name: 'p1' }], error: 'Failed to load', isFetching: true }),
    );
    expect(screen.queryByText("Couldn't load this project")).toBeNull();
    expect(container.querySelector('.violations-skeleton')).toBeTruthy();
    expect(container.querySelector('.loading-screen')).toBeNull();
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

/* Mimics the App wiring (see ViolationsRoute): `subTab` is a route param and
   flipping it REPLACES the nav entry in place — history must not grow per
   flip, so the harness stack length is part of the assertions. */
function SubTabNavHarness({ data, log }) {
  const [stack, setStack] = useState([{}]);
  const top = stack[stack.length - 1];
  return (
    <ViolationsPage
      data={data}
      callbacks={{}}
      subTab={top.subTab || 'dimension'}
      onSubTabChange={(v) => {
        setStack((s) => {
          log.push(['replace', v, s.length]);
          return s.slice(0, -1).concat([{ ...s[s.length - 1], subTab: v }]);
        });
      }}
    />
  );
}

describe('ViolationsPage — sub-tab lives in the nav entry (replace, not push)', () => {
  const DIMS = [{
    dimension: 'security',
    violations: [
      { file: 'src/a.py', severity: 'minor', principle: 'P1' },
      { file: 'lib/b.py', severity: 'major', principle: 'P2' },
    ],
    compliance: [],
  }];
  const data = () => ({
    accumulatedDimensions: DIMS,
    selectedProject: 'p1',
    projects: [{ id: 'p1', name: 'p1' }],
    projectsLoaded: true,
    projectName: 'p1',
    loading: false,
    isFetching: false,
    dismissRefreshKey: 0,
    selectedSource: 'local',
  });

  function renderHarness(log) {
    const QC = withQueryClient();
    return render(
      <QC>
        <SubTabNavHarness data={data()} log={log} />
      </QC>
    );
  }

  it('flipping to by-file and dismissed replaces the entry in place; the view follows the param', async () => {
    const log = [];
    renderHarness(log);
    // Default sub-tab renders the dimension grid.
    expect(await screen.findByText('security')).toBeInTheDocument();

    fireEvent.click(screen.getByText('by-file'));
    // Replace with the stack still at length 1 — a push would report 2 next.
    expect(log).toEqual([['replace', 'file', 1]]);
    // The controlled param round-tripped into the file tree view.
    expect(await screen.findByText('src')).toBeInTheDocument();

    fireEvent.click(screen.getByText('dismissed'));
    expect(log).toEqual([['replace', 'file', 1], ['replace', 'dismissed', 1]]);
    expect(await screen.findByText('No dismissed violations.')).toBeInTheDocument();
  });

  it('renders the sub-tab the route param dictates without any interaction', () => {
    const QC = withQueryClient();
    render(
      <QC>
        <ViolationsPage data={data()} callbacks={{}} subTab="file" onSubTabChange={() => {}} />
      </QC>
    );
    expect(screen.getByText('src')).toBeInTheDocument();
    expect(screen.getByText('lib')).toBeInTheDocument();
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
