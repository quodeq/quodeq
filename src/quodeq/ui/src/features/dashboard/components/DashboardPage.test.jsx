import { render, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage from './DashboardPage.jsx';

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
