import { render, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage, { selectDashboardProjectInfo } from './DashboardPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// First-load flicker guard. On a fresh (uncached) load the dashboard query
// resolves a beat before the scores query. The Overview isn't ready to render
// until `accumulated` (derived from scores) arrives too. If the page drops its
// loading state the moment the dashboard payload lands, it fades to
// `dashboard-ready` (a 400ms fade-in) while still showing a spinner, then the
// real content pops in a beat later: the "it refreshes again" flicker. So the
// Overview must stay in the loading state until BOTH the dashboard and the
// accumulated block are present.
const overviewLoading = {
  projectsLoaded: true,
  projects: [{ id: 'p1', name: 'p1' }],
  selectedProject: 'p1',
  // dashboard payload has already resolved...
  dashboard: {
    dimensions: [{ dimension: 'Security', overallScore: '7.0/10', violations: [], compliance: [], principles: [] }],
    trend: [],
    selectedRun: { runId: 'r1', dateLabel: '2026-05-01' },
  },
  // ...but the scores query has not, so accumulated is still null and `loading`
  // (dashboardQuery.isLoading || scoresLoading) is still true.
  accumulated: null,
  loading: true,
  isFetching: false,
  error: null,
  availableRuns: [{ runId: 'r1', status: 'complete' }],
};

describe('DashboardPage first-load loading gate', () => {
  // P6: the Overview no longer dims .dashboard-page while isLoading -- the
  // OverviewSkeleton rendered inside it IS the content (the dim existed to
  // fade *stale* content under the loader overlay, and there is none here).
  it('keeps the Overview showing the skeleton (not real content) until accumulated (scores) is ready, undimmed', () => {
    const { container } = render(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    expect(page.className).not.toContain('dashboard-loading');
    expect(page.className).toContain('dashboard-ready');
    expect(page.querySelector('.overview-skeleton')).toBeTruthy();
  });

  // Scenario 1 (collision): dashboard has resolved but accumulated hasn't, so
  // DashboardContent used to gate its own `!accumulated` check independently
  // of the page's isLoading -- both the page-level grace loader (message
  // variant) and DashboardContent's own LoadingScreen mounted at once, two
  // overlapping pulsing logos. DashboardContent must not render a loader of
  // its own; readiness is a single decision made by the page.
  // P6: the Overview's loader ladder is the OverviewSkeleton now, not
  // LoadingScreen -- still exactly one, never both.
  it('renders exactly one overview skeleton and no LoadingScreen while dashboard is resolved but accumulated is not', () => {
    const { container } = render(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
    expect(container.querySelectorAll('.loading-screen').length).toBe(0);
    expect(container.querySelectorAll('.overview-skeleton').length).toBe(1);
  });

  // P2 containment, carried over to the skeleton: it renders inside
  // .dashboard-page (never a fixed/fullscreen overlay), so a project switch
  // never covers Sidebar/TopBar. Only the app-level cold-start loader stays
  // fullscreen.
  it('renders the skeleton contained within .dashboard-page, not a fullscreen loader', () => {
    const { container } = render(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
    const page = container.querySelector('.dashboard-page');
    expect(page.querySelector('.overview-skeleton')).toBeTruthy();
    expect(container.querySelector('.loading-screen')).toBeNull();
  });

  // Scenario 8, carried over: the skeleton must never sit inside a dimmed
  // `.dashboard-loading` (opacity .4) container -- there is none for the
  // Overview any more, since the skeleton is the content, not an overlay.
  it('does not dim the container the skeleton lives in', () => {
    const { container } = render(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
    expect(container.querySelector('.dashboard-loading')).toBeNull();
    expect(container.querySelector('.overview-skeleton')).toBeTruthy();
  });

  // The flip side: a cold score cache can take several seconds to rebuild. We
  // must not sit on a blank full-screen spinner that whole time (reads as "the
  // project won't open"). Once the dashboard payload is in and a short grace
  // has elapsed, fall back to the partial page so a slow load shows progress.
  // Rules-of-Hooks guard. On first load `projectsLoaded` is false, which hits
  // an early return; a beat later it flips true and the page renders fully. If
  // any hook (e.g. the grace state) lives BELOW the early returns, the hook
  // count changes between those two renders and React throws #310 — a blank
  // crash on load. This reproduces that transition.
  it('does not change hook count across the projectsLoaded false -> true transition', () => {
    const { rerender } = render(
      <DashboardPage data={{ projectsLoaded: false }} callbacks={{}} runMode={false} />,
    );
    expect(() => {
      rerender(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
    }).not.toThrow();
  });

  // P6: the grace fallback no longer hands off from a skeleton to a
  // LoadingScreen -- the same OverviewSkeleton continues across the flip, so
  // there's no loader/skeleton swap for the user to notice.
  it('continues the same overview skeleton across the grace period if scores stays slow (no loader handoff)', () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
      // Before the grace: skeleton already showing, undimmed.
      expect(container.querySelector('.dashboard-page').className).not.toContain('dashboard-loading');
      expect(container.querySelectorAll('.overview-skeleton').length).toBe(1);
      // After the grace elapses with scores still pending: same skeleton, still
      // exactly one, no LoadingScreen ever mounts, no dim.
      act(() => { vi.advanceTimersByTime(800); });
      expect(container.querySelector('.dashboard-page').className).toContain('dashboard-ready');
      expect(container.querySelectorAll('.overview-skeleton').length).toBe(1);
      expect(container.querySelectorAll('.loading-screen').length).toBe(0);
      expect(container.querySelector('.dashboard-loading')).toBeNull();
      // Same project-name signal the loader it replaced used to carry, now in
      // the skeleton's TermHeader sub.
      expect(container.querySelector('.term-header__sub')?.textContent).toBe('loading p1…');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('DashboardPage no-completed-evaluation empty state', () => {
  // Project has runs (so the `!dashboard` empty state upstream doesn't
  // fire) but none terminated cleanly, and none are in progress -- the
  // NoCompletedEvalPanel branch under test.
  const baseData = {
    projectsLoaded: true,
    projects: [{ id: 'p1', name: 'p1' }],
    selectedProject: 'p1',
    dashboard: {
      dimensions: [],
      trend: [],
      selectedRun: { runId: 'r1', dateLabel: '2026-05-01' },
    },
    accumulated: { dimensions: [] },
    loading: false,
    isFetching: false,
    error: null,
    availableRuns: [{ runId: 'r1', status: 'failed' }],
  };

  it('local project: shows the Start evaluation CTA (existing behavior pinned)', () => {
    const { getByText, queryByText } = render(
      <DashboardPage data={{ ...baseData, selectedSource: 'local' }} callbacks={{}} runMode={false} />,
    );
    expect(getByText('No completed evaluation yet')).toBeTruthy();
    expect(getByText('Start evaluation')).toBeTruthy();
    expect(queryByText('no completed evaluation in this remote project yet')).toBeNull();
  });

  it('shared project: hides the Start evaluation CTA and shows shared-specific copy', () => {
    const { getByText, queryByText } = render(
      <DashboardPage data={{ ...baseData, selectedSource: 'shared' }} callbacks={{}} runMode={false} />,
    );
    expect(getByText('No completed evaluation yet')).toBeTruthy();
    expect(getByText('no completed evaluation in this remote project yet')).toBeTruthy();
    expect(queryByText('Start evaluation')).toBeNull();
  });
});

describe('DashboardPage fetch-failure state', () => {
  // A failed dashboard query leaves dashboard === null with loading and
  // isFetching settled. That used to fall into the "No evaluations yet"
  // empty state, so a 404/500/timeout told the user their evaluations
  // didn't exist (they did). Errors must render as errors.
  const errorData = {
    projectsLoaded: true,
    projects: [{ id: 'p1', name: 'p1' }],
    selectedProject: 'p1',
    dashboard: null,
    accumulated: null,
    loading: false,
    isFetching: false,
    error: 'Failed to load dashboard data. Check your connection and try refreshing.',
    availableRuns: [],
  };

  it('renders an error state, not "No evaluations yet"', () => {
    const { getByText, queryByText } = render(
      <DashboardPage data={errorData} callbacks={{}} runMode={false} />,
    );
    expect(queryByText('No evaluations yet')).toBeNull();
    expect(getByText("Couldn't load this project")).toBeTruthy();
  });

  it('offers a Retry action wired to onRetry', () => {
    const onRetry = vi.fn();
    const { getByText } = render(
      <DashboardPage data={errorData} callbacks={{ onRetry }} runMode={false} />,
    );
    fireEvent.click(getByText('Retry'));
    expect(onRetry).toHaveBeenCalled();
  });

  it('without an error, the settled empty state still says No evaluations yet', () => {
    const { getByText } = render(
      <DashboardPage data={{ ...errorData, error: null }} callbacks={{}} runMode={false} />,
    );
    expect(getByText('No evaluations yet')).toBeTruthy();
  });

  // P4-T2: clicking Retry sets isFetching while loading stays false and
  // error stays set (react-query's shape for a refetch of a query that's
  // already settled into an error). That state used to render the error
  // branch with no feedback at all -- Retry visibly did nothing.
  it('shows the inline loader instead of the error state while a retry is in flight', () => {
    const { container, queryByText } = render(
      <DashboardPage data={{ ...errorData, isFetching: true }} callbacks={{}} runMode={false} />,
    );
    expect(queryByText("Couldn't load this project")).toBeNull();
    expect(container.querySelector('.loading-screen')).toBeTruthy();
  });
});

// P5-T2: the no-runs -> first-run transition. Task 7 removed the redundant
// eval-completion refetch, but the sequence "No evaluations yet" -> (dashboard
// key changes to the new run) -> loader -> content still had two bugs: a
// window-refocus/background refetch of an empty project used to render a
// visually blank .dashboard-page (no dim, no loader), and the post-eval
// selectedRun flip used to swap the empty state for the full inline loader
// for a beat before content landed (empty -> loader -> content pop).
describe('DashboardPage no-runs -> first-run transition (P5-T2)', () => {
  const baseNoRuns = {
    projectsLoaded: true,
    projects: [{ id: 'p1', name: 'p1' }],
    selectedProject: 'p1',
    selectedSource: 'local',
    dashboard: null,
    accumulated: null,
    loading: false,
    isFetching: false,
    error: null,
    availableRuns: [],
  };

  it('blank-frame shape (background refetch of an empty project) shows the dimmed empty state, not a blank frame', () => {
    const { container, getByText } = render(
      <SidePaneProvider>
        <DashboardPage data={{ ...baseNoRuns, isFetching: true }} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    expect(getByText('No evaluations yet')).toBeTruthy();
    expect(container.querySelector('.loading-screen')).toBeNull();
    expect(container.querySelector('.dashboard-page').className).toContain('dashboard-refreshing');
  });

  it('keeps the empty state (dimmed) through the post-eval selectedRun flip, then swaps straight to content', () => {
    const { container, getByText, queryByText, rerender } = render(
      <SidePaneProvider>
        <DashboardPage data={baseNoRuns} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    expect(getByText('No evaluations yet')).toBeTruthy();

    // selectedRun flips to the new run id: new dashboard query key mounts,
    // same project/source, loading true, dashboard still null.
    rerender(
      <SidePaneProvider>
        <DashboardPage data={{ ...baseNoRuns, loading: true, isFetching: true }} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    expect(getByText('No evaluations yet')).toBeTruthy();
    expect(container.querySelector('.loading-screen')).toBeNull();
    expect(container.querySelector('.dashboard-page').className).toContain('dashboard-refreshing');

    const dims = [{ dimension: 'maintainability', overallScore: '7.0/10' }];

    // Finding 2 (P5 final review): the dashboard query settles before the
    // scores query does -- dashboard payload is in, accumulated isn't yet.
    // Releasing the latch here (the pre-fix !dashboard check) swapped the
    // dimmed empty state for the full inline loader for a beat before
    // content landed: a narrower version of the pop this latch exists to
    // close. It must stay on the dimmed empty state instead.
    rerender(
      <SidePaneProvider>
        <DashboardPage
          data={{
            ...baseNoRuns,
            dashboard: { dimensions: dims, trend: [], selectedRun: { runId: 'r1', dateLabel: '2026-07-01' } },
            accumulated: null,
            loading: true,
            isFetching: true,
            availableRuns: [{ runId: 'r1', status: 'complete' }],
          }}
          callbacks={{}}
          runMode={false}
        />
      </SidePaneProvider>,
    );
    expect(getByText('No evaluations yet')).toBeTruthy();
    expect(container.querySelector('.loading-screen')).toBeNull();
    expect(container.querySelector('.dashboard-page').className).toContain('dashboard-refreshing');

    rerender(
      <SidePaneProvider>
        <DashboardPage
          data={{
            ...baseNoRuns,
            dashboard: { dimensions: dims, trend: [], selectedRun: { runId: 'r1', dateLabel: '2026-07-01' } },
            accumulated: { dimensions: dims },
            loading: false,
            isFetching: false,
            availableRuns: [{ runId: 'r1', status: 'complete' }],
          }}
          callbacks={{}}
          runMode={false}
        />
      </SidePaneProvider>,
    );
    expect(queryByText('No evaluations yet')).toBeNull();
    expect(container.querySelector('.loading-screen')).toBeNull();
  });

  it('resets the stickiness on a project switch: the skeleton shows, not the previous project\'s empty state', () => {
    const { container, getByText, queryByText, rerender } = render(
      <SidePaneProvider>
        <DashboardPage data={baseNoRuns} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    expect(getByText('No evaluations yet')).toBeTruthy();

    rerender(
      <SidePaneProvider>
        <DashboardPage
          data={{
            ...baseNoRuns,
            selectedProject: 'p2',
            projects: [{ id: 'p2', name: 'p2' }],
            loading: true,
            isFetching: true,
          }}
          callbacks={{}}
          runMode={false}
        />
      </SidePaneProvider>,
    );
    expect(queryByText('No evaluations yet')).toBeNull();
    expect(container.querySelector('.overview-skeleton')).toBeTruthy();
    expect(container.querySelector('.loading-screen')).toBeNull();
  });

  it('runMode is excluded from the no-runs empty state, and instead renders a run-appropriate empty state (not a blank frame)', () => {
    const onRetry = vi.fn();
    const { container, getByText, queryByText } = render(
      <SidePaneProvider>
        <DashboardPage data={{ ...baseNoRuns, selectedRun: 'r1' }} callbacks={{ onRetry }} runMode={true} />
      </SidePaneProvider>,
    );
    expect(queryByText('No evaluations yet')).toBeNull();
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    expect(page.children.length).toBeGreaterThan(0);
    expect(getByText("Couldn't load this run")).toBeTruthy();
    fireEvent.click(getByText('Retry'));
    expect(onRetry).toHaveBeenCalled();
  });

  it('runMode: shows the inline loader (not the run-appropriate empty state) while a retry of a falsy response is in flight', () => {
    const { container, queryByText } = render(
      <SidePaneProvider>
        <DashboardPage data={{ ...baseNoRuns, selectedRun: 'r1', isFetching: true }} callbacks={{}} runMode={true} />
      </SidePaneProvider>,
    );
    expect(queryByText("Couldn't load this run")).toBeNull();
    expect(container.querySelector('.loading-screen')).toBeTruthy();
  });

  it('a runMode round-trip does not clear the overview sticky latch for the same project+source', () => {
    const { getByText, rerender } = render(
      <SidePaneProvider>
        <DashboardPage data={baseNoRuns} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    expect(getByText('No evaluations yet')).toBeTruthy();

    // User opens a run detail view for the same project+source, then returns
    // to Overview without DashboardPage ever unmounting (App.jsx's key is the
    // activeTab, which doesn't change when the run page's sourceTab is
    // 'overview' -- see useAppState.js).
    rerender(
      <SidePaneProvider>
        <DashboardPage data={{ ...baseNoRuns, selectedRun: 'r1' }} callbacks={{}} runMode={true} />
      </SidePaneProvider>,
    );

    // Back to Overview mid-flip (post-eval selectedRun change): the sticky
    // latch must still be active from the very first render, not cleared by
    // the runMode pass in between.
    rerender(
      <SidePaneProvider>
        <DashboardPage data={{ ...baseNoRuns, loading: true, isFetching: true }} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    expect(getByText('No evaluations yet')).toBeTruthy();
  });
});

// Scenario 2 (collision): runMode renders RunOverviewPanel, which has its own
// inline loading state (`!dashboard.dimensions`). Before the page's own
// isLoading/DashboardContent-mount decision accounted for that, the page-level
// grace loader and RunOverviewPanel's inline spinner could both mount at once.
describe('DashboardPage runMode loading gate', () => {
  const runModeLoading = {
    projectsLoaded: true,
    projects: [{ id: 'p1', name: 'p1' }],
    selectedProject: 'p1',
    selectedRun: 'r1',
    dashboard: null,
    accumulated: null,
    loading: true,
    isFetching: false,
    error: null,
    availableRuns: [{ runId: 'r1', status: 'complete' }],
  };

  it('renders exactly one LoadingScreen before the run payload has resolved', () => {
    const { container } = render(
      <SidePaneProvider>
        <DashboardPage data={runModeLoading} callbacks={{}} runMode={true} />
      </SidePaneProvider>,
    );
    expect(container.querySelectorAll('.loading-screen').length).toBe(1);
    expect(container.querySelector('.loading-screen').className).toContain('loading-screen--inline');
  });

  it('renders exactly one LoadingScreen once the run payload resolves without dimensions yet', () => {
    const { container } = render(
      <SidePaneProvider>
        <DashboardPage
          data={{
            ...runModeLoading,
            dashboard: { selectedRun: { runId: 'r1', dateLabel: '2026-05-01' }, trend: [] },
          }}
          callbacks={{}}
          runMode={true}
        />
      </SidePaneProvider>,
    );
    expect(container.querySelectorAll('.loading-screen').length).toBe(1);
  });
});

// Teammate persona (shared-repo onboarding): a teammate with ZERO local
// projects selects a shared project. The local-list empty-state gate must not
// wall off the Overview when the selection is shared -- the shared data loads
// fine and its own loading/empty states take over. Same gate class already
// fixed on MapPage/HistoryPage/ViolationsPage.
describe('DashboardPage, teammate persona: shared selection + zero local projects', () => {
  const sharedNoLocalData = {
    projectsLoaded: true,
    projects: [],
    selectedProject: 'shared-1',
    selectedSource: 'shared',
    sharedProjectInfo: { id: 'shared-1', name: 'shared-1', displayName: 'Shared Repo' },
    dashboard: {
      dimensions: [],
      trend: [],
      selectedRun: { runId: 'r1', dateLabel: '2026-05-01' },
    },
    accumulated: { dimensions: [] },
    loading: false,
    isFetching: false,
    error: null,
    availableRuns: [{ runId: 'r1', status: 'failed' }],
  };

  it('shared source with an empty LOCAL projects list renders the shared content path, not the Add-a-project wall', () => {
    const { getByText, queryByText } = render(
      <DashboardPage data={sharedNoLocalData} callbacks={{}} runMode={false} />,
    );
    expect(queryByText('No projects yet')).toBeNull();
    expect(queryByText('Add a project')).toBeNull();
    expect(getByText('no completed evaluation in this remote project yet')).toBeTruthy();
  });

  it('local source with an empty local projects list still shows the Add-a-project wall (unchanged)', () => {
    const { getByText } = render(
      <DashboardPage
        data={{ ...sharedNoLocalData, selectedSource: 'local', selectedProject: '', sharedProjectInfo: null }}
        callbacks={{}}
        runMode={false}
      />,
    );
    expect(getByText('No projects yet')).toBeTruthy();
  });

  // Remote-content awareness: zero local projects + a shared repo with
  // published content must route to the repositories tab, not dead-end on
  // "Add a project" (spec 2026-07-23-remote-repos-without-local-projects).
  it('local source, zero local projects, shared content: offers Browse remote repositories', () => {
    const onNavigate = vi.fn();
    const { getByText, queryByText } = render(
      <DashboardPage
        data={{ ...sharedNoLocalData, selectedSource: 'local', selectedProject: '', sharedProjectInfo: null, sharedHasContent: true }}
        callbacks={{ onNavigate }}
        runMode={false}
      />,
    );
    expect(getByText('No local projects yet')).toBeTruthy();
    expect(queryByText('No projects yet')).toBeNull();
    fireEvent.click(getByText('Browse remote repositories'));
    expect(onNavigate).toHaveBeenCalledWith('projects');
  });

  it('local source, zero local projects, NO shared content: unchanged Add-a-project wall', () => {
    const { getByText } = render(
      <DashboardPage
        data={{ ...sharedNoLocalData, selectedSource: 'local', selectedProject: '', sharedProjectInfo: null, sharedHasContent: false }}
        callbacks={{}}
        runMode={false}
      />,
    );
    expect(getByText('No projects yet')).toBeTruthy();
    expect(getByText('Add a project')).toBeTruthy();
  });
});

// P4: the Overview's frame must stay mounted across every state, including
// the "no projects"/"no project selected" empty branches -- otherwise the
// page jumps (no .dashboard-page wrapper, then one appears) the moment real
// content shows up. The error and no-completed-evaluation branches already
// wrap in .dashboard-page; these bare EmptyState returns did not.
describe('DashboardPage frame stability in empty branches', () => {
  const zeroLocalProjectsData = {
    projectsLoaded: true,
    projects: [],
    selectedSource: 'local',
    selectedProject: '',
    sharedProjectInfo: null,
    dashboard: null,
    accumulated: { dimensions: [] },
    loading: false,
    isFetching: false,
    error: null,
    availableRuns: [],
  };

  it('wraps the no-local-projects (local source) empty state in .dashboard-page', () => {
    const { container, getByText } = render(
      <DashboardPage
        data={{ ...zeroLocalProjectsData, sharedHasContent: false }}
        callbacks={{}}
        runMode={false}
      />,
    );
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    expect(page.contains(getByText('No projects yet'))).toBe(true);
  });

  it('wraps the no-local-projects-but-shared-content empty state in .dashboard-page', () => {
    const { container, getByText } = render(
      <DashboardPage
        data={{ ...zeroLocalProjectsData, sharedHasContent: true }}
        callbacks={{}}
        runMode={false}
      />,
    );
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    expect(page.contains(getByText('No local projects yet'))).toBe(true);
  });

  it('wraps the no-project-selected empty state in .dashboard-page', () => {
    const { container, getByText } = render(
      <DashboardPage
        data={{ projectsLoaded: true, projects: [{ id: 'p1', name: 'p1' }], selectedProject: '', loading: false, isFetching: false, error: null, availableRuns: [] }}
        callbacks={{}}
        runMode={false}
      />,
    );
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    expect(page.contains(getByText('No project selected'))).toBe(true);
  });
});

// P3-T2: the page-level frame must survive every branch transition (no
// div<->Fragment root-type flip), and `dashboard-fadein` must play once per
// project/source/run context instead of replaying on every loading<->ready
// flip or branch swap over unchanged content.
describe('DashboardPage frame stability and fade-once across branch transitions (P3-T2)', () => {
  const readyOverview = {
    projectsLoaded: true,
    projects: [{ id: 'p1', name: 'p1' }],
    selectedProject: 'p1',
    selectedSource: 'local',
    dashboard: {
      dimensions: [{ dimension: 'Security', overallScore: '7.0/10', violations: [], compliance: [], principles: [] }],
      trend: [],
      selectedRun: { runId: 'r1', dateLabel: '2026-05-01' },
    },
    accumulated: { dimensions: [{ dimension: 'Security', overallScore: '7.0/10' }] },
    loading: false,
    isFetching: false,
    error: null,
    availableRuns: [{ runId: 'r1', status: 'complete' }],
  };

  it('keeps the same .dashboard-page DOM node across a transition from an early-return branch to the main content branch', () => {
    const { container, rerender } = render(
      <SidePaneProvider>
        <DashboardPage data={{ projectsLoaded: true, projects: [{ id: 'p1', name: 'p1' }], selectedProject: '', loading: false, isFetching: false, error: null, availableRuns: [] }} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    const nodeBefore = container.querySelector('.dashboard-page');
    expect(nodeBefore).toBeTruthy();

    rerender(
      <SidePaneProvider>
        <DashboardPage data={readyOverview} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    const nodeAfter = container.querySelector('.dashboard-page');
    expect(nodeAfter).toBeTruthy();
    expect(nodeAfter).toBe(nodeBefore);
  });

  it('keeps the same .dashboard-page DOM node across a transition from the error branch to the main content branch', () => {
    const { container, rerender } = render(
      <SidePaneProvider>
        <DashboardPage
          data={{ projectsLoaded: true, projects: [{ id: 'p1', name: 'p1' }], selectedProject: 'p1', dashboard: null, accumulated: null, loading: false, isFetching: false, error: 'boom', availableRuns: [] }}
          callbacks={{}}
          runMode={false}
        />
      </SidePaneProvider>,
    );
    const nodeBefore = container.querySelector('.dashboard-page');
    expect(nodeBefore).toBeTruthy();

    rerender(
      <SidePaneProvider>
        <DashboardPage data={readyOverview} callbacks={{}} runMode={false} />
      </SidePaneProvider>,
    );
    const nodeAfter = container.querySelector('.dashboard-page');
    expect(nodeAfter).toBe(nodeBefore);
  });

  it('carries dashboard-appear on first content appearance, holds it through unrelated re-renders for the animation window, then releases', () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(
        <SidePaneProvider>
          <DashboardPage data={{ ...readyOverview, accumulated: null, loading: true }} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      let page = container.querySelector('.dashboard-page');
      // P6: the Overview never dims -- the skeleton is showing here, undimmed --
      // but it's still "still loading" for the appear latch's purposes.
      expect(page.className).not.toContain('dashboard-loading');
      expect(page.className).toContain('dashboard-ready');
      expect(page.className).not.toContain('dashboard-appear');
      expect(page.querySelector('.overview-skeleton')).toBeTruthy();

      rerender(
        <SidePaneProvider>
          <DashboardPage data={readyOverview} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-ready');
      expect(page.className).toContain('dashboard-appear');

      // An unrelated re-render inside the animation window (isFetching
      // flipping a moment after content appeared) must NOT drop the class:
      // that snapped opacity to 1 and cut the fade short.
      rerender(
        <SidePaneProvider>
          <DashboardPage data={{ ...readyOverview, isFetching: true }} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-ready');
      expect(page.className).toContain('dashboard-refreshing');
      expect(page.className).toContain('dashboard-appear');

      // Once the animation window has passed, the class releases -- and a
      // further render over the same context must not re-add it.
      act(() => { vi.advanceTimersByTime(450); });
      page = container.querySelector('.dashboard-page');
      expect(page.className).not.toContain('dashboard-appear');
      rerender(
        <SidePaneProvider>
          <DashboardPage data={readyOverview} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      page = container.querySelector('.dashboard-page');
      expect(page.className).not.toContain('dashboard-appear');
    } finally {
      vi.useRealTimers();
    }
  });

  // P6 fix: the appear latch's read AND write are gated on `!showOverviewSkeleton`
  // (DashboardPage.jsx, beside `dashboardAppearKey`). Before that gate, the
  // grace-elapsed flip replayed a 400ms fade over the already-visible,
  // unchanged skeleton (a flash) and spent the latch early, so real content
  // got no fade at all. Now: no fade while the skeleton continues across the
  // flip, and the fade is reserved for when DashboardContent actually mounts.
  it('does not fade the skeleton at the grace-elapsed flip, and fires dashboard-appear once real content mounts', () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(
        <SidePaneProvider>
          <DashboardPage data={{ ...readyOverview, accumulated: null, loading: true }} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      act(() => { vi.advanceTimersByTime(800); });
      // Grace elapsed, accumulated still not in: the skeleton continues
      // (same as before the flip) -- must not fade, that would flash it.
      let page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-ready');
      expect(page.className).not.toContain('dashboard-appear');
      expect(page.querySelector('.overview-skeleton')).toBeTruthy();

      rerender(
        <SidePaneProvider>
          <DashboardPage data={readyOverview} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      // Real content mounts for the first time in this context: this is what
      // gets the fade, not the earlier grace-elapsed flip.
      page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-ready');
      expect(page.className).toContain('dashboard-appear');
      expect(page.querySelector('.overview-skeleton')).toBeNull();

      rerender(
        <SidePaneProvider>
          <DashboardPage data={{ ...readyOverview, isFetching: true }} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      // Still inside the animation window: the hold keeps the fade running.
      page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-appear');
      // After the window: released, and no replay over the same context.
      act(() => { vi.advanceTimersByTime(450); });
      page = container.querySelector('.dashboard-page');
      expect(page.className).not.toContain('dashboard-appear');
    } finally {
      vi.useRealTimers();
    }
  });

  // Fast path: content lands well before the grace timer would fire (the
  // common case). isLoading and contentReady flip in the same render, so the
  // showOverviewSkeleton gate never engages and the fade plays exactly as it
  // did before this fix.
  it('plays dashboard-appear normally when content arrives before the grace timer fires', () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(
        <SidePaneProvider>
          <DashboardPage data={{ ...readyOverview, accumulated: null, loading: true }} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      // Partway through the grace window -- timer still pending, not fired.
      act(() => { vi.advanceTimersByTime(300); });
      let page = container.querySelector('.dashboard-page');
      expect(page.className).not.toContain('dashboard-appear');

      rerender(
        <SidePaneProvider>
          <DashboardPage data={readyOverview} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-ready');
      expect(page.className).toContain('dashboard-appear');
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not replay dashboard-appear when the sticky no-runs empty state hands off to real content', () => {
    const baseNoRuns = {
      projectsLoaded: true,
      projects: [{ id: 'p1', name: 'p1' }],
      selectedProject: 'p1',
      selectedSource: 'local',
      dashboard: null,
      accumulated: null,
      loading: false,
      isFetching: false,
      error: null,
      availableRuns: [],
    };
    vi.useFakeTimers();
    try {
      const { container, rerender, getByText, queryByText } = render(
        <SidePaneProvider>
          <DashboardPage data={baseNoRuns} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      expect(getByText('No evaluations yet')).toBeTruthy();
      let page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-appear');
      act(() => { vi.advanceTimersByTime(450); });

      rerender(
        <SidePaneProvider>
          <DashboardPage data={{ ...readyOverview, selectedProject: 'p1', selectedSource: 'local' }} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      expect(queryByText('No evaluations yet')).toBeNull();
      page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-ready');
      expect(page.className).not.toContain('dashboard-appear');
    } finally {
      vi.useRealTimers();
    }
  });

  it('re-arms dashboard-appear on a project switch (a new context gets its own fade)', () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(
        <SidePaneProvider>
          <DashboardPage data={readyOverview} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      let page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-appear');
      act(() => { vi.advanceTimersByTime(450); });

      rerender(
        <SidePaneProvider>
          <DashboardPage data={{ ...readyOverview, isFetching: true }} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      page = container.querySelector('.dashboard-page');
      expect(page.className).not.toContain('dashboard-appear');

      const project2 = {
        ...readyOverview,
        selectedProject: 'p2',
        projects: [{ id: 'p2', name: 'p2' }],
        dashboard: { ...readyOverview.dashboard, selectedRun: { runId: 'r2', dateLabel: '2026-06-01' } },
      };
      rerender(
        <SidePaneProvider>
          <DashboardPage data={project2} callbacks={{}} runMode={false} />
        </SidePaneProvider>,
      );
      page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-appear');
    } finally {
      vi.useRealTimers();
    }
  });

  it('re-arms dashboard-appear on a run switch in run-detail, but not on a repeat render of the same run', () => {
    const readyRun = (runId) => ({
      projectsLoaded: true,
      projects: [{ id: 'p1', name: 'p1' }],
      selectedProject: 'p1',
      selectedSource: 'local',
      selectedRun: runId,
      dashboard: {
        dimensions: [{ dimension: 'Security', overallScore: '7.0/10', violations: [], compliance: [], principles: [] }],
        trend: [],
        selectedRun: { runId, dateLabel: '2026-05-01' },
      },
      accumulated: null,
      loading: false,
      isFetching: false,
      error: null,
      availableRuns: [{ runId, status: 'complete' }],
    });

    vi.useFakeTimers();
    try {
      const { container, rerender } = render(
        <SidePaneProvider>
          <DashboardPage data={readyRun('r1')} callbacks={{}} runMode={true} />
        </SidePaneProvider>,
      );
      let page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-appear');
      act(() => { vi.advanceTimersByTime(450); });

      // Same run re-rendered (e.g. an unrelated prop changing): must not replay.
      rerender(
        <SidePaneProvider>
          <DashboardPage data={{ ...readyRun('r1'), isFetching: true }} callbacks={{}} runMode={true} />
        </SidePaneProvider>,
      );
      page = container.querySelector('.dashboard-page');
      expect(page.className).not.toContain('dashboard-appear');

      // Switching to a different run in run-detail is a legitimate new context.
      rerender(
        <SidePaneProvider>
          <DashboardPage data={readyRun('r2')} callbacks={{}} runMode={true} />
        </SidePaneProvider>,
      );
      page = container.querySelector('.dashboard-page');
      expect(page.className).toContain('dashboard-appear');
    } finally {
      vi.useRealTimers();
    }
  });
});

// Finding 5 (final whole-branch review): projectInfo for a shared selection
// must come from the shared-repo fetch (sharedProjectInfo, see useDashboard),
// never the LOCAL projects list -- a shared selection's id can collide with
// an unrelated local project (e.g. after a clone-on-add pull), and looking it
// up locally would bleed the local twin's stats/publishedBy into a shared
// Overview. Unit-tested against the exported selector directly (mounting the
// full Overview render needs a SidePaneProvider + more, which is its own
// integration concern -- AccumulatedHeroSection's own tests already pin the
// "renders publishedBy given correct projectInfo" half of this contract).
describe('selectDashboardProjectInfo', () => {
  const localTwin = { id: 'proj-1', name: 'proj-1', displayName: 'Local Twin', languageStats: { js: 999 } };
  const sharedInfo = { id: 'proj-1', name: 'proj-1', displayName: 'Shared View', publishedBy: 'ana', languageStats: { py: 5 } };

  it('shared source: returns the shared fetch result, never the id-colliding local twin', () => {
    const info = selectDashboardProjectInfo({
      selectedSource: 'shared', projects: [localTwin], selectedProject: 'proj-1', sharedProjectInfo: sharedInfo,
    });
    expect(info).toBe(sharedInfo);
    expect(info.publishedBy).toBe('ana');
  });

  it('shared source before the fetch resolves: null, not a silent fallback to the local list', () => {
    const info = selectDashboardProjectInfo({
      selectedSource: 'shared', projects: [localTwin], selectedProject: 'proj-1', sharedProjectInfo: null,
    });
    expect(info).toBeNull();
  });

  it('local source: unchanged -- looks up the local projects list by id/name', () => {
    const info = selectDashboardProjectInfo({
      selectedSource: 'local', projects: [localTwin], selectedProject: 'proj-1', sharedProjectInfo: sharedInfo,
    });
    expect(info).toBe(localTwin);
  });

  it('local source with no match: null', () => {
    const info = selectDashboardProjectInfo({
      selectedSource: 'local', projects: [], selectedProject: 'proj-1', sharedProjectInfo: sharedInfo,
    });
    expect(info).toBeNull();
  });
});

// v1.9.0 regression: when the startup projects fetch exhausted its retries the
// page sat on the fullscreen LoadingScreen forever -- projectsLoaded stayed
// false with no error branch above this gate and nothing left to re-fire the
// load. The gate must surface a retry instead of an unrecoverable spinner.
describe('projects-load failure gate (startup infinite spinner)', () => {
  it('renders a retry action instead of a LoadingScreen when the projects load failed', () => {
    const onProjectsRetry = vi.fn();
    const { container } = render(
      <DashboardPage
        data={{ projectsLoaded: false, projectsLoadFailed: true }}
        callbacks={{ onProjectsRetry }}
        runMode={false}
      />,
    );
    expect(container.querySelector('.loading-screen')).toBeNull();
    const btn = container.querySelector('.empty-state-btn');
    expect(btn).toBeTruthy();
    fireEvent.click(btn);
    expect(onProjectsRetry).toHaveBeenCalledTimes(1);
  });

  it('renders nothing at the gate while the load is in flight (the app-level overlay covers it)', () => {
    const { container } = render(
      <DashboardPage data={{ projectsLoaded: false, projectsLoadFailed: false }} callbacks={{}} runMode={false} />,
    );
    // The loader lives at one stable app-level mount (FadingLoadingScreen)
    // so it can fade out; a second copy here would stack tips on tips.
    expect(container.querySelector('.loading-screen')).toBeNull();
    expect(container.querySelector('.empty-state-btn')).toBeNull();
    expect(container.firstChild).toBeNull();
  });

  it('does not change hook count across the failed -> loaded transition', () => {
    const { rerender } = render(
      <DashboardPage data={{ projectsLoaded: false, projectsLoadFailed: true }} callbacks={{}} runMode={false} />,
    );
    expect(() => {
      rerender(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
    }).not.toThrow();
  });
});

describe('warm-up surfaces', () => {
  it('renders no loader of its own before projects load (app-level overlay owns that state)', () => {
    const warmup = { active: true, projectsDone: 0, projectsTotal: 2, currentProjectName: 'x' };
    const { container } = render(
      <DashboardPage data={{ projectsLoaded: false, warmup }} callbacks={{}} runMode={false} />,
    );
    expect(container.querySelector('.loading-screen')).toBeNull();
    expect(container.querySelector('.warmup-notice')).toBeNull();
  });

  it('shows the warm-up notice above the overview skeleton while scores compute', () => {
    const warmup = { active: true, projectsDone: 1, projectsTotal: 6, currentProjectName: 'my-app' };
    const { container } = render(
      <DashboardPage data={{ ...overviewLoading, warmup }} callbacks={{}} runMode={false} />,
    );
    expect(container.querySelector('.overview-skeleton')).toBeTruthy();
    expect(container.querySelector('.warmup-notice')).toBeTruthy();
  });

  it('renders no warm-up notice when the snapshot is inactive', () => {
    const { container } = render(
      <DashboardPage data={{ ...overviewLoading, warmup: { active: false, projectsDone: 2, projectsTotal: 2 } }} callbacks={{}} runMode={false} />,
    );
    expect(container.querySelector('.warmup-notice')).toBeNull();
  });
});
