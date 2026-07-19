import { render, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage, { selectDashboardProjectInfo } from './DashboardPage.jsx';

// First-load flicker guard. On a fresh (uncached) load the dashboard query
// resolves a beat before the scores query. The Overview renders nothing until
// `accumulated` (derived from scores) arrives — DashboardContent returns a
// LoadingScreen without it. If the page drops its loading state the moment the
// dashboard payload lands, it fades to `dashboard-ready` (a 400ms fade-in)
// while still showing a spinner, then the real content pops in a beat later:
// the "it refreshes again" flicker. So the Overview must stay in the loading
// state until BOTH the dashboard and the accumulated block are present.
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
  it('keeps the Overview in the loading state until accumulated (scores) is ready', () => {
    const { container } = render(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    // Must NOT flip to the ready fade before the data needed to render is present.
    expect(page.className).toContain('dashboard-loading');
    expect(page.className).not.toContain('dashboard-ready');
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

  it('falls back to the partial page after a grace period if scores stays slow', () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<DashboardPage data={overviewLoading} callbacks={{}} runMode={false} />);
      // Before the grace: still the full loading screen.
      expect(container.querySelector('.dashboard-page').className).toContain('dashboard-loading');
      // After the grace elapses with scores still pending: drop to the partial page.
      act(() => { vi.advanceTimersByTime(800); });
      expect(container.querySelector('.dashboard-page').className).toContain('dashboard-ready');
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
    expect(queryByText('no completed evaluation in this shared project yet')).toBeNull();
  });

  it('shared project: hides the Start evaluation CTA and shows shared-specific copy', () => {
    const { getByText, queryByText } = render(
      <DashboardPage data={{ ...baseData, selectedSource: 'shared' }} callbacks={{}} runMode={false} />,
    );
    expect(getByText('No completed evaluation yet')).toBeTruthy();
    expect(getByText('no completed evaluation in this shared project yet')).toBeTruthy();
    expect(queryByText('Start evaluation')).toBeNull();
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
    expect(getByText('no completed evaluation in this shared project yet')).toBeTruthy();
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
