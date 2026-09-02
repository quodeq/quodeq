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

// Split from App.test.jsx: error/onRetry threading to Violations/Map/
// History, buildAssistantActionAppliedHandler, the assistant drawer's
// shared-project close gate, and the evaluate route's shared fallback.

// P4-T2: Violations/Map/History previously never received the dashboard
// bundle's error/onRetry (see App.jsx's buildDashboardDataBundle) -- a fetch
// failure on those routes had no way to surface an error state or a working
// Retry. These pin the threading only; the pages' own render decisions are
// covered in their own test files.
describe('error/onRetry threading to Violations/Map/History (P4-T2)', () => {
  it('ViolationsRoute threads error and onRetry from the dashboard data bundle', () => {
    const props = {
      dashboardData: {
        latestAccumulated: null, accumulated: null, selectedDisplayName: 'p1',
        loading: false, isFetching: false, error: 'boom', onRetry: vi.fn(),
      },
      navigation: { selectedProject: 'proj1', selectedSource: 'local', projects: [], projectsLoaded: true, handleNavigate: vi.fn(), navStackLength: 1 },
      dismissRefreshKey: 0,
      refreshDashboard: vi.fn(),
      scheduleDashboardReconcile: vi.fn(),
    };
    const outer = ROUTE_RENDERERS.violations({}, props);
    const inner = outer.type(outer.props);
    expect(inner.props.data.error).toBe('boom');
    expect(inner.props.callbacks.onRetry).toBe(props.dashboardData.onRetry);
  });

  it('the map renderer threads error and onRetry from the dashboard data bundle', () => {
    const props = {
      dashboardData: {
        latestAccumulated: null, accumulated: null, dashboard: null, selectedDisplayName: 'p1',
        loading: false, isFetching: false, error: 'boom', onRetry: vi.fn(),
      },
      navigation: { selectedProject: 'proj1', selectedSource: 'local', projects: [], projectsLoaded: true, handleNavigate: vi.fn(), navStackLength: 1 },
      refreshDashboard: vi.fn(),
    };
    const el = ROUTE_RENDERERS.map({}, props);
    expect(el.props.data.error).toBe('boom');
    expect(el.props.callbacks.onRetry).toBe(props.dashboardData.onRetry);
  });

  it('the history renderer threads error and onRetry from the dashboard data bundle', () => {
    const props = {
      dashboardData: {
        dashboard: { trend: [] }, availableRuns: [], overviewRunIndex: 0,
        accumulated: null, loading: false, isFetching: false, error: 'boom', onRetry: vi.fn(),
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
    expect(el.props.error).toBe('boom');
    expect(el.props.onRetry).toBe(props.dashboardData.onRetry);
  });
});

// An assistant-applied dismiss mutates exactly the payloads a manual dismiss
// does, so it owes the same convergence follow-ups the manual paths got: the
// instant delta patch, the dismissed-list bump, the lazy mark-stale, AND the
// debounced ACTIVE reconcile. The reconcile is the one that reaches the
// Overview -- its useDashboard observer is mounted at the app root and never
// remounts, and pywebview never fires a focus-refetch -- so without it, any
// view the delta doesn't cover keeps showing pre-dismiss numbers, which is
// the "nothing updated" symptom the manual paths were fixed for.
describe('buildAssistantActionAppliedHandler', () => {
  function deps(overrides = {}) {
    return {
      applyDelta: vi.fn(),
      bumpDismissRefresh: vi.fn(),
      scheduleDashboardReconcile: vi.fn(),
      selectedProject: 'proj1',
      ...overrides,
    };
  }

  const dismissEvent = (detail) => ({ detail: { actionType: 'dismiss_finding', ...detail } });

  it('schedules the active dashboard reconcile after a dismiss apply', () => {
    const d = deps();
    buildAssistantActionAppliedHandler(d)(dismissEvent({ delta: { project: 'proj1' }, scores: {} }));
    expect(d.scheduleDashboardReconcile).toHaveBeenCalledTimes(1);
  });

  it('bumps the dismissed list alongside the reconcile', () => {
    const d = deps();
    buildAssistantActionAppliedHandler(d)(dismissEvent({ delta: { project: 'proj1' }, scores: {} }));
    expect(d.bumpDismissRefresh).toHaveBeenCalledTimes(1);
  });

  // The regression this pins: a dismiss whose response carries no delta at
  // all has NOTHING patching the visible screen, so the reconcile is the only
  // path back to correct numbers. Skipping it here would be silently wrong.
  it('still reconciles when the apply response carries no delta to patch', () => {
    const d = deps();
    buildAssistantActionAppliedHandler(d)(dismissEvent({}));
    expect(d.applyDelta).not.toHaveBeenCalled();
    expect(d.scheduleDashboardReconcile).toHaveBeenCalledTimes(1);
  });

  // applyDelta writes into a project-keyed cache, so it must use the delta's
  // frozen project rather than the live selection (the apply POST can resolve
  // after a project switch). The reconcile is only a refetch, so it stays on
  // the live selection -- aiming it wrong re-pulls data, it never corrupts.
  it('patches the delta against the delta\'s own project, not the live selection', () => {
    const d = deps({ selectedProject: 'proj2' });
    buildAssistantActionAppliedHandler(d)(dismissEvent({ delta: { project: 'proj1' }, scores: { dimensions: [] } }));
    expect(d.applyDelta).toHaveBeenCalledWith('proj1', { dimensions: [] }, { project: 'proj1' });
  });

  it('falls back to the live selection when the delta names no project', () => {
    const d = deps({ selectedProject: 'proj2' });
    buildAssistantActionAppliedHandler(d)(dismissEvent({ delta: { some: 'delta' }, scores: {} }));
    expect(d.applyDelta).toHaveBeenCalledWith('proj2', {}, { some: 'delta' });
  });

  // The patch is best-effort; a throw must not swallow the follow-ups that
  // are the actual convergence guarantee.
  it('still reconciles when the delta patch throws', () => {
    const d = deps({ applyDelta: vi.fn(() => { throw new Error('bad delta'); }) });
    buildAssistantActionAppliedHandler(d)(dismissEvent({ delta: { project: 'proj1' }, scores: {} }));
    expect(d.scheduleDashboardReconcile).toHaveBeenCalledTimes(1);
  });

  it('ignores assistant actions that are not dismissals', () => {
    const d = deps();
    buildAssistantActionAppliedHandler(d)({ detail: { actionType: 'verify_finding', delta: {} } });
    expect(d.applyDelta).not.toHaveBeenCalled();
    expect(d.bumpDismissRefresh).not.toHaveBeenCalled();
    expect(d.scheduleDashboardReconcile).not.toHaveBeenCalled();
  });

  it('tolerates an event with no detail at all', () => {
    const d = deps();
    expect(() => buildAssistantActionAppliedHandler(d)({})).not.toThrow();
    expect(d.scheduleDashboardReconcile).not.toHaveBeenCalled();
  });
});

describe('Assistant drawer close on shared project switch', () => {
  // Task 19: shared projects have no mutation routes (dismiss/verify are
  // local-only). The drawer must close when switching to shared to prevent
  // writes to the local store under a shared project's id. The effect in
  // App.jsx guards both drawer close AND session re-bind on selectedSource.
  it('isSharedSource returns true for shared selections', () => {
    expect(isSharedSource('shared')).toBe(true);
  });

  it('isSharedSource returns false for local selections', () => {
    expect(isSharedSource('local')).toBe(false);
  });
});

// Final whole-branch review, Critical 1 (belt-and-braces): there is no
// Evaluate flow for shared projects. shouldShowEvaluateButton already keeps
// the TopBar from linking here, but a stale nav-stack entry could still land
// the router on the 'evaluate' route with a shared selection -- it must fall
// back to the Overview rather than rendering the dead-end evaluate screen.
describe('evaluate route: shared-source fallback (Critical 1 belt-and-braces)', () => {
  function baseProps(selectedSource) {
    const projects = [{ id: 'proj1', name: 'proj1' }];
    return {
      navigation: {
        selectedProject: 'proj1', selectedSource, projects,
        handleNavigate: vi.fn(), handleRunSelect: vi.fn(), loadProjects: vi.fn(),
      },
      dashboardData: { selectedProject: 'proj1', selectedSource, projects, projectsLoaded: true },
      serverHealth: { connected: true, setConnected: vi.fn() },
      evaluation: {},
    };
  }

  it('renders the Evaluate screen for a local selection', () => {
    const el = ROUTE_RENDERERS.evaluate({}, baseProps('local'));
    // EvaluateCase's own prop shape -- distinct from what the overview route renders.
    expect(el.props).toHaveProperty('onGoToProjects');
    expect(el.props).toHaveProperty('selectedProject', 'proj1');
  });

  it('falls back to exactly what the overview route renders for a shared selection', () => {
    const props = baseProps('shared');
    const evalEl = ROUTE_RENDERERS.evaluate({}, props);
    const overviewEl = ROUTE_RENDERERS.overview({}, props);
    expect(evalEl.type).toBe(overviewEl.type);
    expect(evalEl.props).not.toHaveProperty('onGoToProjects');
  });
});
