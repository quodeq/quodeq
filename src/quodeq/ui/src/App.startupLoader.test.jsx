import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {
  buildEvalPrincipal, ROUTE_RENDERERS, isSharedSource, shouldBounceToEvaluate, shouldShowEvaluateButton,
  resolveSelectionAfterSharedDisconnect, shouldAutoOpenOnboardingWizard, shouldRedirectToRemoteRepositories, shouldShowProjectTabs,
  buildNavigationBundle, buildDashboardDataBundle, shouldWallEmptyProjects, buildWizardHandlers, buildAssistantSessionPayload,
  buildAssistantActionAppliedHandler, resolveProjectDisplayName, selectSidebarCounts,
  shouldShowStartupLoader,
} from './App.jsx';
import Sidebar from './components/Sidebar.jsx';

// Split from App.test.jsx: history route onRunDeleted wiring,
// projects-load-failure threading, and shouldShowStartupLoader.

// Deleting a run changes the accumulated rollup the Overview grade is built
// from -- the same class of mutation as dismiss/restore/delete-finding, which
// all get the debounced ACTIVE reconcile. mark-stale alone leaves the
// always-mounted Overview observer on pre-deletion numbers indefinitely
// (pywebview never fires a focus refetch).
describe('history route onRunDeleted wiring', () => {
  it('wires onRunDeleted to the debounced active reconcile, not mark-stale only', () => {
    const props = {
      dashboardData: {
        dashboard: { trend: [] }, availableRuns: [], overviewRunIndex: 0,
        accumulated: null, loading: false, isFetching: false,
      },
      navigation: {
        selectedProject: 'proj1', selectedSource: 'local', projects: [],
        projectsLoaded: true, handleNavigate: vi.fn(), historySelectedRun: null,
        setHistorySelectedRun: vi.fn(),
      },
      refreshDashboard: vi.fn(),
      scheduleDashboardReconcile: vi.fn(),
    };
    const el = ROUTE_RENDERERS.history({}, props);
    el.props.callbacks.onRunDeleted();
    expect(props.scheduleDashboardReconcile).toHaveBeenCalledTimes(1);
  });
});

// v1.9.0 startup-spinner regression: the failure state and its retry action
// must survive both explicit bundle whitelists (see buildDashboardDataBundle's
// docstring -- an unforwarded field silently arrives as undefined and the
// feature never activates).
describe('projects-load failure threading', () => {
  it('buildDashboardDataBundle forwards projectsLoadFailed and the retry action', () => {
    const state = { projectsLoadFailed: true, retryLoadProjects: vi.fn() };
    const bundle = buildDashboardDataBundle({ state });
    expect(bundle.projectsLoadFailed).toBe(true);
    expect(bundle.onProjectsRetry).toBe(state.retryLoadProjects);
  });

  it('buildNavigationBundle forwards projectsLoadFailed and retryLoadProjects', () => {
    const state = { projectsLoadFailed: true, retryLoadProjects: vi.fn() };
    const bundle = buildNavigationBundle({
      state, navTab: vi.fn(), navStackLength: 1, isEvaluating: false,
      showToast: vi.fn(), setWizardEntry: vi.fn(),
    });
    expect(bundle.projectsLoadFailed).toBe(true);
    expect(bundle.retryLoadProjects).toBe(state.retryLoadProjects);
  });

  it('the overview route threads onProjectsRetry into DashboardPage callbacks', () => {
    const props = {
      dashboardData: { projectsLoaded: false, projectsLoadFailed: true, onProjectsRetry: vi.fn() },
      navigation: { handleNavigate: vi.fn(), handleRunSelect: vi.fn(), loadProjects: vi.fn() },
    };
    const el = ROUTE_RENDERERS.overview({}, props);
    expect(el.props.callbacks.onProjectsRetry).toBe(props.dashboardData.onProjectsRetry);
  });

  it('the run route threads onProjectsRetry into DashboardPage callbacks', () => {
    const props = {
      dashboardData: { projectsLoaded: false, projectsLoadFailed: true, onProjectsRetry: vi.fn() },
      navigation: { handleNavigate: vi.fn() },
    };
    const el = ROUTE_RENDERERS.run({}, props);
    expect(el.props.callbacks.onProjectsRetry).toBe(props.dashboardData.onProjectsRetry);
  });

  it('both bundles forward the warmup snapshot', () => {
    const warmup = { active: true, projectsDone: 0, projectsTotal: 2, currentProjectName: 'x' };
    const state = { warmup };
    expect(buildDashboardDataBundle({ state }).warmup).toBe(warmup);
    expect(buildNavigationBundle({
      state, navTab: vi.fn(), navStackLength: 1, isEvaluating: false,
      showToast: vi.fn(), setWizardEntry: vi.fn(),
    }).warmup).toBe(warmup);
  });
});

// The startup loader must outlive projectsLoaded: dropping it there hands the
// user a skeleton flash (loader > skeleton > data) on every boot. It holds
// until the Overview's data is in, and drops immediately on any dead end
// where no data will ever arrive (failure, zero projects, nothing selected,
// query error, or the user restored into a different tab).
describe('shouldShowStartupLoader', () => {
  const base = {
    projectsLoaded: true, projectsLoadFailed: false, projectsCount: 2,
    selectedProject: 'proj-1', selectedSource: 'local', activeTab: 'overview',
    dashboard: null, accumulated: null, error: null, loading: true,
  };

  it('shows before projects load', () => {
    expect(shouldShowStartupLoader({ ...base, projectsLoaded: false })).toBe(true);
  });

  it('shows before projects load regardless of the restored tab', () => {
    expect(shouldShowStartupLoader({ ...base, projectsLoaded: false, activeTab: 'settings' })).toBe(true);
  });

  it('drops on projects load failure (retry state must be reachable)', () => {
    expect(shouldShowStartupLoader({ ...base, projectsLoaded: false, projectsLoadFailed: true })).toBe(false);
  });

  it('holds after projects load while overview data is still loading', () => {
    expect(shouldShowStartupLoader(base)).toBe(true);
  });

  it('keeps holding when only the dashboard payload has arrived', () => {
    expect(shouldShowStartupLoader({ ...base, dashboard: { runs: [] } })).toBe(true);
  });

  it('drops once dashboard and accumulated are both in', () => {
    expect(shouldShowStartupLoader({ ...base, dashboard: { runs: [] }, accumulated: { dims: [] } })).toBe(false);
  });

  it('drops on a dashboard query error (error state must be reachable)', () => {
    expect(shouldShowStartupLoader({ ...base, error: new Error('boom') })).toBe(false);
  });

  it('drops with zero local projects (onboarding/empty states take over)', () => {
    expect(shouldShowStartupLoader({ ...base, projectsCount: 0, selectedProject: null })).toBe(false);
  });

  it('holds for a shared selection even with zero local projects', () => {
    expect(shouldShowStartupLoader({ ...base, projectsCount: 0, selectedSource: 'shared' })).toBe(true);
  });

  it('drops when nothing is selected', () => {
    expect(shouldShowStartupLoader({ ...base, selectedProject: null })).toBe(false);
  });

  it('drops when the user restored into a non-overview tab', () => {
    expect(shouldShowStartupLoader({ ...base, activeTab: 'violations' })).toBe(false);
  });

  it('drops when the queries settle with no data coming (project with no completed evaluations)', () => {
    // accumulated stays null forever for a run-less project; only `loading`
    // (dashboard + scores queries combined) says nothing more is in flight.
    // Without this escape the loader would wall off the empty state forever.
    expect(shouldShowStartupLoader({ ...base, loading: false })).toBe(false);
  });

  it('keeps holding while either query is still in flight even with partial data', () => {
    expect(shouldShowStartupLoader({ ...base, dashboard: { runs: [] }, loading: true })).toBe(true);
  });
});
