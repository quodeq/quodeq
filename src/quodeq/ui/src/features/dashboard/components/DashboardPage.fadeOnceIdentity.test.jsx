import { render, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage, { selectDashboardProjectInfo } from './DashboardPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// Split from DashboardPage.test.jsx: frame-node identity across branch
// transitions and the dashboard-appear fade-once contract (P3-T2),
// part 1 (DOM-node identity + the first-appearance/grace-elapsed fade).

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
});
