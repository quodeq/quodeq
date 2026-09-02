import { render, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage, { selectDashboardProjectInfo } from './DashboardPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// Split from DashboardPage.test.jsx: the first-load skeleton gate,
// no-completed-evaluation empty state, and the fetch-failure state.

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
