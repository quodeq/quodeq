import { render, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage, { selectDashboardProjectInfo } from './DashboardPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// Split from DashboardPage.test.jsx: the no-runs -> first-run transition
// (P5-T2).

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
