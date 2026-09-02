import { render, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage, { selectDashboardProjectInfo } from './DashboardPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// Split from DashboardPage.test.jsx: the selectDashboardProjectInfo
// selector, the projects-load-failure startup gate, and warm-up notices.

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
