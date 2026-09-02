import { render, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage, { selectDashboardProjectInfo } from './DashboardPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// Split from DashboardPage.test.jsx: dashboard-appear fade-once (P3-T2),
// part 2 (no-replay on empty-state handoff, re-arm on project/run switch).

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
