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

// Pins the contract that App.jsx's ``buildEvalPrincipal`` threads the
// dimension's run id into ``evalPrincipal.runId``. Without it, the dismiss
// POST from PrincipleDetail (when navigated from the Violations or Map
// pages) lands at the backend with no usable ``run_id`` — the rescore
// returns ``null`` and the grade never updates.

describe('buildEvalPrincipal', () => {
  const principleObj = {
    principle: 'Input Validation',
    dimension: 'Security',
    violations: [],
    compliance: [],
  };
  const principleGrade = { score: '7.0/10', grade: 'B' };

  it('threads runId from the originating accumulated dimension', () => {
    const result = buildEvalPrincipal(principleObj, principleGrade, 'run-abc');
    expect(result.runId).toBe('run-abc');
  });

  it('falls back to empty string when no runId is provided', () => {
    const result = buildEvalPrincipal(principleObj, principleGrade);
    expect(result.runId).toBe('');
  });

  it('preserves principle, dimension, score, and grade fields', () => {
    const result = buildEvalPrincipal(principleObj, principleGrade, 'run-abc');
    expect(result.principle).toBe('Input Validation');
    expect(result.dimension).toBe('Security');
    expect(result.score).toBe('7.0/10');
    expect(result.grade).toBe('B');
  });
});

// Task 19 — read-only gating for shared projects. Shared projects have no
// mutation route on the backend (dismiss/restore/delete/evaluate are
// local-only by design, and a shared project's id can collide with a local
// one). These pin the source-gating contract at the seams App.jsx actually
// wires up, without mounting the whole App (which needs ~8 providers).

describe('isSharedSource', () => {
  it('is true for "shared"', () => expect(isSharedSource('shared')).toBe(true));
  it('is false for "local"', () => expect(isSharedSource('local')).toBe(false));
  it('is false for undefined', () => expect(isSharedSource(undefined)).toBe(false));
});

describe('shouldShowEvaluateButton', () => {
  it('shows Evaluate when projects exist and source is local', () => {
    expect(shouldShowEvaluateButton(3, 'local')).toBe(true);
  });
  it('hides Evaluate for a shared selection even with projects present', () => {
    expect(shouldShowEvaluateButton(3, 'shared')).toBe(false);
  });
  it('hides Evaluate when there are no projects at all', () => {
    expect(shouldShowEvaluateButton(0, 'local')).toBe(false);
  });
});

describe('shouldBounceToEvaluate', () => {
  const base = {
    projectsLoaded: true,
    projectsCount: 2,
    selectedProjectInfo: { runsCount: 0 },
    hasCurrentProjectRuns: false,
    activeTab: 'overview',
    selectedSource: 'local',
  };

  it('bounces a local project with zero runs on a project-data tab', () => {
    expect(shouldBounceToEvaluate(base)).toBe(true);
  });

  it('never bounces a shared selection, even when hasCurrentProjectRuns is false', () => {
    // The regression this guards: selectedProjectInfo is looked up in the
    // LOCAL project list, so a shared project whose id collides with a local
    // one could read a misleading (local) runsCount of 0 while the shared
    // source has real data. There is no Evaluate flow for shared projects at
    // all, so source must gate independent of hasCurrentProjectRuns.
    expect(shouldBounceToEvaluate({ ...base, selectedSource: 'shared' })).toBe(false);
  });

  it('does not bounce before projects have loaded', () => {
    expect(shouldBounceToEvaluate({ ...base, projectsLoaded: false })).toBe(false);
  });

  it('does not bounce when there are no projects', () => {
    expect(shouldBounceToEvaluate({ ...base, projectsCount: 0 })).toBe(false);
  });

  it('does not bounce while selectedProjectInfo has not resolved yet', () => {
    expect(shouldBounceToEvaluate({ ...base, selectedProjectInfo: null })).toBe(false);
  });

  it('does not bounce on a tab that is not overview/violations/map/history', () => {
    expect(shouldBounceToEvaluate({ ...base, activeTab: 'settings' })).toBe(false);
  });

  it('does not bounce once the project already has runs', () => {
    expect(shouldBounceToEvaluate({ ...base, hasCurrentProjectRuns: true })).toBe(false);
  });
});

describe('ROUTE_RENDERERS onDismiss source gating', () => {
  function baseProps(selectedSource) {
    return {
      navigation: { selectedProject: 'proj1', selectedRun: 'latest', selectedSource, projects: [] },
      dismissFinding: vi.fn().mockResolvedValue({ scores: { dimensions: [] }, delta: {} }),
      applyDelta: vi.fn(),
      refreshDashboard: vi.fn(),
      scheduleDashboardReconcile: vi.fn(),
      bumpDismissRefresh: vi.fn(),
    };
  }

  it('file route wires up onDismiss for a local project', () => {
    const el = ROUTE_RENDERERS.file({ file: { path: 'a.py' }, runId: 'r1' }, baseProps('local'));
    expect(typeof el.props.onDismiss).toBe('function');
  });

  it('file route passes onDismiss as undefined for a shared project', () => {
    const el = ROUTE_RENDERERS.file({ file: { path: 'a.py' }, runId: 'r1' }, baseProps('shared'));
    expect(el.props.onDismiss).toBeUndefined();
  });

  it('finding route wires up onDismiss for a local project', () => {
    const el = ROUTE_RENDERERS.finding({ finding: {}, principle: 'P', dimension: 'Security' }, baseProps('local'));
    expect(typeof el.props.onDismiss).toBe('function');
  });

  it('finding route passes onDismiss as undefined for a shared project', () => {
    const el = ROUTE_RENDERERS.finding({ finding: {}, principle: 'P', dimension: 'Security' }, baseProps('shared'));
    expect(el.props.onDismiss).toBeUndefined();
  });

  it('evalprinciple route wires up onDismiss for a local project', () => {
    const el = ROUTE_RENDERERS.evalprinciple({ evalPrincipal: { principle: 'P', dimension: 'Security' } }, baseProps('local'));
    expect(typeof el.props.onDismiss).toBe('function');
  });

  it('evalprinciple route passes onDismiss as undefined for a shared project', () => {
    const el = ROUTE_RENDERERS.evalprinciple({ evalPrincipal: { principle: 'P', dimension: 'Security' } }, baseProps('shared'));
    expect(el.props.onDismiss).toBeUndefined();
  });

  it('eval-principle-detail (alias route) also gates onDismiss for a shared project', () => {
    const el = ROUTE_RENDERERS['eval-principle-detail']({ evalPrincipal: { principle: 'P', dimension: 'Security' } }, baseProps('shared'));
    expect(el.props.onDismiss).toBeUndefined();
  });

  // The dismiss-identity contract, parametrized over EVERY dismissing route:
  // a cross-project entry (Compare's jumps, a parent dimension's fromProject)
  // must dismiss into the project the finding belongs to, never the global
  // selection. Third instance of this divergence class (assistant dismiss,
  // evalprinciple, file) — this test closes it: a new dismissing route with
  // a cross-project param belongs in this table.
  describe.each([
    ['file', { file: { path: 'a.py' }, runId: 'r1', fromProject: 'other-proj' }, { file: { path: 'a.py' }, runId: 'r1' }],
    ['finding', { finding: {}, principle: 'P', dimension: 'Security', runId: 'r1', fromProject: 'other-proj' }, { finding: {}, principle: 'P', dimension: 'Security', runId: 'r1' }],
    ['evalprinciple', { evalPrincipal: { principle: 'P', dimension: 'Security', project: 'other-proj', runId: 'r1' } }, { evalPrincipal: { principle: 'P', dimension: 'Security' } }],
  ])('%s route dismiss identity', (route, foreignParams, localParams) => {
    const violation = { file: 'a.py', line: 1, principle: 'P', severity: 'major', reason: 'r' };

    it('dismisses into the entry own project when it differs from the selection', async () => {
      const props = baseProps('local');
      const el = ROUTE_RENDERERS[route](foreignParams, props);
      await el.props.onDismiss(violation);
      expect(props.dismissFinding).toHaveBeenCalledWith('other-proj', expect.any(Object));
      expect(props.applyDelta).toHaveBeenCalledWith('other-proj', expect.anything(), expect.anything());
    });

    it('falls back to the selected project when the entry carries none', async () => {
      const props = baseProps('local');
      const el = ROUTE_RENDERERS[route](localParams, props);
      await el.props.onDismiss(violation);
      expect(props.dismissFinding).toHaveBeenCalledWith('proj1', expect.any(Object));
    });
  });

  // The dashboard must eventually reflect a dismiss even though the delta
  // patch is only best-effort (e.g. it doesn't cover every view). Each
  // onDismiss success path makes ONE reconcile call: scheduleDashboardReconcile
  // marks the project queries stale synchronously AND actively refetches the
  // always-mounted Overview observer after the debounce (see useDashboard.js),
  // so a separate refreshDashboard call would be redundant.
  it('file route onDismiss calls scheduleDashboardReconcile and bumpDismissRefresh on success', async () => {
    const props = baseProps('local');
    const el = ROUTE_RENDERERS.file({ file: { path: 'a.py' }, runId: 'r1' }, props);
    await el.props.onDismiss({ reason: 'test' });
    expect(props.scheduleDashboardReconcile).toHaveBeenCalledTimes(1);
    expect(props.refreshDashboard).not.toHaveBeenCalled();
    expect(props.bumpDismissRefresh).toHaveBeenCalledTimes(1);
  });

  it('finding route onDismiss calls scheduleDashboardReconcile and bumpDismissRefresh on success', async () => {
    const props = baseProps('local');
    const el = ROUTE_RENDERERS.finding({ finding: {}, principle: 'P', dimension: 'Security' }, props);
    await el.props.onDismiss({ reason: 'test' });
    expect(props.scheduleDashboardReconcile).toHaveBeenCalledTimes(1);
    expect(props.refreshDashboard).not.toHaveBeenCalled();
    expect(props.bumpDismissRefresh).toHaveBeenCalledTimes(1);
  });

  it('evalprinciple route onDismiss calls scheduleDashboardReconcile and bumpDismissRefresh on success', async () => {
    const props = baseProps('local');
    const el = ROUTE_RENDERERS.evalprinciple({ evalPrincipal: { principle: 'P', dimension: 'Security' } }, props);
    await el.props.onDismiss({ reason: 'test' });
    expect(props.scheduleDashboardReconcile).toHaveBeenCalledTimes(1);
    expect(props.refreshDashboard).not.toHaveBeenCalled();
    expect(props.bumpDismissRefresh).toHaveBeenCalledTimes(1);
  });
});

// ViolationsPage fires its onRefresh on every mount (see
// ViolationsPage.jsx's tabKey effect) -- including plain drill-down/back
// navigation with no mutation involved, since the page remounts on every
// round trip. Wiring onRefresh to scheduleDashboardReconcile (as a prior
// revision did) turned every such round trip into an ACTIVE refetch of the
// 10-20 MB dashboard payload -- the exact freeze refetchType:'none' exists
// to avoid. onRefresh must stay wired to the lazy refreshDashboard; only the
// four suppression-mutation handlers in useDismissedFindings.js (restore/
// restore-all/delete/delete-all) get the debounced ACTIVE reconcile, via the
// separate onReconcile callback threaded down from here.
describe('ViolationsRoute onRefresh/onReconcile wiring (Dismissed tab reconcile)', () => {
  function renderViolationsRoute(props) {
    const outer = ROUTE_RENDERERS.violations({}, props);
    // ROUTE_RENDERERS.violations returns <ViolationsRoute params props />;
    // ViolationsRoute itself has no hooks, so invoking it directly (the way
    // React would) is safe without mounting a component tree.
    return outer.type(outer.props);
  }

  function violationsProps() {
    return {
      dashboardData: { latestAccumulated: null, accumulated: null, selectedDisplayName: 'p1', loading: false, isFetching: false },
      navigation: { selectedProject: 'proj1', selectedSource: 'local', projects: [], projectsLoaded: true, handleNavigate: vi.fn(), navStackLength: 1 },
      dismissRefreshKey: 0,
      refreshDashboard: vi.fn(),
      scheduleDashboardReconcile: vi.fn(),
    };
  }

  it('wires onRefresh to refreshDashboard (lazy mark-stale) so plain navigation never forces an active refetch', () => {
    const props = violationsProps();
    const inner = renderViolationsRoute(props);
    expect(inner.props.callbacks.onRefresh).toBe(props.refreshDashboard);
    expect(inner.props.callbacks.onRefresh).not.toBe(props.scheduleDashboardReconcile);
  });

  it('wires onReconcile to scheduleDashboardReconcile, for the suppression-mutation handlers to call in addition to onRefresh', () => {
    const props = violationsProps();
    const inner = renderViolationsRoute(props);
    expect(inner.props.callbacks.onReconcile).toBe(props.scheduleDashboardReconcile);
  });
});

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

// Important 3: the onboarding wizard must not auto-open over a teammate's
// working shared-project view just because state.projects (the LOCAL list)
// is empty.
describe('shouldAutoOpenOnboardingWizard', () => {
  const base = { projectsLoaded: true, projectsCount: 0, selectedSource: 'local', isEvaluating: false };

  it('opens for a fresh local install (no projects, local source, not evaluating)', () => {
    expect(shouldAutoOpenOnboardingWizard(base)).toBe(true);
  });

  it('does not open for a shared selection even with zero local projects', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, selectedSource: 'shared' })).toBe(false);
  });

  it('does not open before projects have loaded', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, projectsLoaded: false })).toBe(false);
  });

  it('does not open once local projects exist', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, projectsCount: 3 })).toBe(false);
  });

  it('does not open while an evaluation is running', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, isEvaluating: true })).toBe(false);
  });

  // Remote-content awareness: a configured shared repo with published
  // projects is a working view the user can browse — the wizard must not
  // open over it (spec 2026-07-23-remote-repos-without-local-projects).
  it('defers (no open) while the shared-repo signal has not settled', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, sharedSettled: false })).toBe(false);
  });

  it('does not open when the shared repo has content', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, sharedSettled: true, sharedHasContent: true })).toBe(false);
  });

  it('opens when the shared repo settled without content', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, sharedSettled: true, sharedHasContent: false })).toBe(true);
  });
});

// One-shot landing decision: a fresh start with zero local projects but
// remote content lands on the repositories tab instead of the dead-end
// 'overview' empty state. Latched in App once inputs settle — these tests
// pin the pure decision only.
describe('shouldRedirectToRemoteRepositories', () => {
  const base = {
    projectsLoaded: true, projectsCount: 0, selectedSource: 'local',
    sharedSettled: true, sharedHasContent: true, activeTab: 'overview',
  };

  it('redirects a fresh start: zero local projects, remote content, default overview landing', () => {
    expect(shouldRedirectToRemoteRepositories(base)).toBe(true);
  });

  it('does not redirect before local projects load', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, projectsLoaded: false })).toBe(false);
  });

  it('does not redirect before the shared signal settles', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, sharedSettled: false })).toBe(false);
  });

  it('does not redirect when local projects exist', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, projectsCount: 2 })).toBe(false);
  });

  it('does not redirect over a restored shared selection (already a working view)', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, selectedSource: 'shared' })).toBe(false);
  });

  it('does not redirect without remote content', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, sharedHasContent: false })).toBe(false);
  });

  it('does not redirect off a non-default tab the user already navigated to', () => {
    expect(shouldRedirectToRemoteRepositories({ ...base, activeTab: 'settings' })).toBe(false);
  });
});

// Sidebar tab gating must be source-aware. hasCurrentProjectRuns is derived
// from the LOCAL project list, so a shared selection with no local mirror
// resolves to null info / zero runs and the four project-data tabs vanish
// even though every one of those pages works for shared projects. The shared
// signal is the resolved sharedProjectInfo (already fetched at App level by
// useDashboard): the shared info payload carries no runsCount at all, and a
// project only appears in the shared repo once published with runs, so
// presence of its info is the correct "has data to show" signal.
describe('shouldShowProjectTabs', () => {
  it('shows tabs for a local project with runs', () => {
    expect(shouldShowProjectTabs({
      selectedSource: 'local', hasCurrentProjectRuns: true, sharedProjectInfo: null,
    })).toBe(true);
  });

  it('hides tabs for a local project with zero runs', () => {
    expect(shouldShowProjectTabs({
      selectedSource: 'local', hasCurrentProjectRuns: false, sharedProjectInfo: null,
    })).toBe(false);
  });

  it('shows tabs for a shared selection once its shared info has resolved, ignoring the local run count', () => {
    expect(shouldShowProjectTabs({
      selectedSource: 'shared',
      hasCurrentProjectRuns: false, // no local mirror -> the local signal reads empty
      sharedProjectInfo: { id: 'team-proj', name: 'team-proj' },
    })).toBe(true);
  });

  it('hides tabs for a shared selection while its shared info has not resolved', () => {
    expect(shouldShowProjectTabs({
      selectedSource: 'shared', hasCurrentProjectRuns: false, sharedProjectInfo: null,
    })).toBe(false);
  });

  it('ignores a colliding local twin\'s shared info for a local selection', () => {
    // A shared project's id can collide with a local one by design. When the
    // LOCAL twin is selected, the gate must read the local run count, not the
    // leftover shared info object.
    expect(shouldShowProjectTabs({
      selectedSource: 'local', hasCurrentProjectRuns: false, sharedProjectInfo: { id: 'team-proj' },
    })).toBe(false);
  });
});

// Scenario 7 (collision): the sidebar's violations/history badges must not
// keep showing the OUTGOING project's numbers once a project switch is in
// flight. `accumulated`/`dashboard` already reset to null the instant
// `selectedProject` changes (samePlaceholderScope, api/queryKeys.js), so
// reading straight off them here is what clears the badges immediately
// instead of holding onto stale numbers until the new project's fetch lands.
describe('selectSidebarCounts', () => {
  it('reads violations/history counts off the filtered view when present', () => {
    const result = selectSidebarCounts({
      filteredAccumulated: { summary: { totalViolations: 12 } },
      accumulated: { summary: { totalViolations: 99 } },
      filteredTrend: [{ runId: 'r1' }, { runId: 'r2' }],
      dashboard: { trend: [{ runId: 'r1' }] },
    });
    expect(result.violationsCount).toBe(12);
    expect(result.historyCount).toBe(2);
  });

  it('falls back to the unfiltered accumulated/dashboard when the filtered view has nothing', () => {
    const result = selectSidebarCounts({
      filteredAccumulated: null,
      accumulated: { summary: { totalViolations: 7 } },
      filteredTrend: [],
      dashboard: { trend: [{ runId: 'r1' }, { runId: 'r2' }] },
    });
    expect(result.violationsCount).toBe(7);
    expect(result.historyCount).toBe(2);
  });

  it('clears both counts on a project switch, before the new project data lands', () => {
    const result = selectSidebarCounts({
      filteredAccumulated: null,
      accumulated: null,
      filteredTrend: [],
      dashboard: null,
    });
    expect(result.violationsCount).toBeNull();
    expect(result.historyCount).toBeNull();
  });
});

describe('Sidebar project-data tabs for a shared-only selection (component)', () => {
  const DATA_TABS = ['overview', 'violations', 'map', 'history'];

  it('renders all four data tabs when the shared project info has resolved', () => {
    const show = shouldShowProjectTabs({
      selectedSource: 'shared',
      hasCurrentProjectRuns: false, // shared-only: no local mirror
      sharedProjectInfo: { id: 'team-proj', name: 'team-proj' },
    });
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} selectedSource="shared" showProjectTabs={show} />);
    for (const tab of DATA_TABS) {
      expect(screen.getByTitle(tab)).toBeInTheDocument();
    }
  });

  it('hides the data tabs while the shared info is still loading', () => {
    const show = shouldShowProjectTabs({
      selectedSource: 'shared', hasCurrentProjectRuns: false, sharedProjectInfo: null,
    });
    render(<Sidebar activeTab="overview" onNavTab={vi.fn()} selectedSource="shared" showProjectTabs={show} />);
    for (const tab of DATA_TABS) {
      expect(screen.queryByTitle(tab)).toBeNull();
    }
  });
});

// A shared/remote project is NOT in the LOCAL projects list, so
// selectedProjectInfo (a local-list lookup) is null and selectedDisplayName
// stays equal to the raw UUID -- the anti-UUID guard then suppressed the
// topbar/sidebar title entirely for remote projects. The name lives in the
// resolved sharedProjectInfo payload; resolveProjectDisplayName must fall back
// to it for shared sources.
describe('resolveProjectDisplayName', () => {
  it('uses the local project name when the selection is local', () => {
    expect(resolveProjectDisplayName({
      selectedProjectInfo: { name: 'growstuff' }, selectedSource: 'local',
      sharedProjectInfo: null, selectedDisplayName: 'growstuff', selectedProject: 'uuid-1',
    })).toBe('growstuff');
  });

  it('falls back to the shared project name for a remote selection not in the local list', () => {
    expect(resolveProjectDisplayName({
      selectedProjectInfo: null, selectedSource: 'shared',
      sharedProjectInfo: { name: 'selectives-ios' },
      selectedDisplayName: 'b6e548aa', selectedProject: 'b6e548aa',
    })).toBe('selectives-ios');
  });

  it('does not borrow a stale shared name for a local selection', () => {
    expect(resolveProjectDisplayName({
      selectedProjectInfo: null, selectedSource: 'local',
      sharedProjectInfo: { name: 'stale-remote' },
      selectedDisplayName: 'uuid-2', selectedProject: 'uuid-2',
    })).toBeNull();
  });

  it('still suppresses the raw UUID while the lists are unresolved', () => {
    expect(resolveProjectDisplayName({
      selectedProjectInfo: null, selectedSource: 'shared', sharedProjectInfo: null,
      selectedDisplayName: 'uuid-3', selectedProject: 'uuid-3',
    })).toBeNull();
  });
});

// PR #819 regression class: a route renderer started consuming a navigation
// key (handleNavigateReplace) that the bundle App builds never forwarded --
// the repositories local/online tab click threw "handleNavigateReplace is
// not a function" and the tab never flipped. The bundle producer is exported
// as buildNavigationBundle so producer and consumer can be pinned together
// without mounting the whole App.
describe('buildNavigationBundle', () => {
  function stubState() {
    return {
      selectedProject: 'p1', selectedSource: 'local', selectedRun: 'latest',
      projects: [{ id: 'p1', name: 'p1' }], projectsLoaded: true,
      loadProjects: vi.fn(),
      handleNavigate: vi.fn(), handleNavigateReplace: vi.fn(), handleRunSelect: vi.fn(),
      handleProjectChange: vi.fn(),
      handleDeleteProject: vi.fn(), handleExportProject: vi.fn(),
      handleRelocateProject: vi.fn(), handleImportProject: vi.fn(),
      historySelectedRun: 'latest', setHistorySelectedRun: vi.fn(),
      currentOverviewRun: null, handleRunPrev: vi.fn(), handleRunNext: vi.fn(), handleRunLatest: vi.fn(),
      prefetchHandlers: {},
    };
  }
  const build = (state) => buildNavigationBundle({
    state, navTab: vi.fn(), navStackLength: 1,
    isEvaluating: false, showToast: vi.fn(), setWizardEntry: vi.fn(),
  });

  it('forwards handleNavigateReplace from state (repositories filter flips die without it)', () => {
    const state = stubState();
    const bundle = build(state);
    bundle.handleNavigateReplace('projects', { filters: { query: '', location: 'shared', sort: 'activity' } });
    expect(state.handleNavigateReplace).toHaveBeenCalledWith('projects', { filters: { query: '', location: 'shared', sort: 'activity' } });
  });

  it("projects route's onFiltersChange reaches state.handleNavigateReplace through the real bundle", () => {
    // Producer x consumer: the element ROUTE_RENDERERS.projects builds must
    // find every navigation key it consumes in the bundle App actually
    // provides -- this is the seam the #819 regression slipped through.
    const state = stubState();
    const el = ROUTE_RENDERERS.projects({}, { navigation: build(state) });
    const filters = { query: '', location: 'shared', sort: 'activity' };
    el.props.actions.onFiltersChange(filters);
    expect(state.handleNavigateReplace).toHaveBeenCalledWith('projects', { filters });
    expect(state.handleNavigate).not.toHaveBeenCalled();
  });
});

// Same pattern as the compare tab's dimension drill-down (PR #1087): the
// map's viz path and the violations sub-tab are route params, so the browser
// back button and the breadcrumb see them. Drilling pushes, navigating up to
// a path already in the trailing run of map entries unwinds history via
// navGoTo, and view toggles replace in place so flipping never grows
// history. Params must be spread forward on every hop or _tabKey (the
// fresh-tab-click reset signal) silently drops and the page resets its
// cached state mid-drill.
describe('map/violations view state lives in the nav stack', () => {
  function mapProps(navOverrides = {}) {
    return {
      dashboardData: {
        latestAccumulated: null, accumulated: null, dashboard: null,
        selectedDisplayName: 'p1', loading: false, isFetching: false,
      },
      navigation: {
        selectedProject: 'p1', selectedSource: 'local', projects: [], projectsLoaded: true,
        handleNavigate: vi.fn(), handleNavigateReplace: vi.fn(), navGoTo: vi.fn(),
        navStack: [{ page: 'map', _tabKey: 3 }], navStackLength: 1,
        ...navOverrides,
      },
      refreshDashboard: vi.fn(),
    };
  }

  it('map: drilling to a new path pushes, with existing params spread forward', () => {
    const props = mapProps();
    const el = ROUTE_RENDERERS.map({ _tabKey: 3, vizStyle: 'riskmatrix' }, props);
    el.props.nav.onPathChange('src');
    expect(props.navigation.handleNavigate).toHaveBeenCalledWith('map', { _tabKey: 3, vizStyle: 'riskmatrix', path: 'src' });
    expect(props.navigation.navGoTo).not.toHaveBeenCalled();
    expect(props.navigation.handleNavigateReplace).not.toHaveBeenCalled();
  });

  it('map: navigating up to a path already in the trailing map trail unwinds via navGoTo, never pushes a duplicate', () => {
    const props = mapProps({
      navStack: [
        { page: 'map', _tabKey: 3 },
        { page: 'map', _tabKey: 3, path: 'src' },
        { page: 'map', _tabKey: 3, path: 'src/app' },
      ],
      navStackLength: 3,
    });
    const el = ROUTE_RENDERERS.map({ _tabKey: 3, path: 'src/app' }, props);
    el.props.nav.onPathChange('');
    expect(props.navigation.navGoTo).toHaveBeenCalledWith(0);
    expect(props.navigation.handleNavigate).not.toHaveBeenCalled();
  });

  it('map: the trail scan stops at the first non-map entry, so an older unrelated map entry is not a goTo target', () => {
    const props = mapProps({
      navStack: [
        { page: 'map', _tabKey: 2, path: 'src' },
        { page: 'overview' },
        { page: 'map', _tabKey: 3, path: 'src/app' },
      ],
      navStackLength: 3,
    });
    const el = ROUTE_RENDERERS.map({ _tabKey: 3, path: 'src/app' }, props);
    el.props.nav.onPathChange('src');
    expect(props.navigation.navGoTo).not.toHaveBeenCalled();
    expect(props.navigation.handleNavigate).toHaveBeenCalledWith('map', { _tabKey: 3, path: 'src' });
  });

  it('map: mode/style toggles replace the entry in place, params preserved', () => {
    const props = mapProps();
    const el = ROUTE_RENDERERS.map({ _tabKey: 3, path: 'src' }, props);
    el.props.nav.onVizStyleChange('galaxy');
    expect(props.navigation.handleNavigateReplace).toHaveBeenCalledWith('map', { _tabKey: 3, path: 'src', vizStyle: 'galaxy' });
    el.props.nav.onGalaxyModeChange('standards');
    expect(props.navigation.handleNavigateReplace).toHaveBeenCalledWith('map', { _tabKey: 3, path: 'src', galaxyMode: 'standards' });
    expect(props.navigation.handleNavigate).not.toHaveBeenCalled();
  });

  it('violations: the sub-tab flip replaces the entry (history must not grow), _tabKey preserved', () => {
    const props = {
      dashboardData: { latestAccumulated: null, accumulated: null, selectedDisplayName: 'p1', loading: false, isFetching: false },
      navigation: {
        selectedProject: 'p1', selectedSource: 'local', projects: [], projectsLoaded: true,
        handleNavigate: vi.fn(), handleNavigateReplace: vi.fn(), navStackLength: 1,
      },
      dismissRefreshKey: 0,
      refreshDashboard: vi.fn(),
      scheduleDashboardReconcile: vi.fn(),
    };
    const outer = ROUTE_RENDERERS.violations({ _tabKey: 2 }, props);
    const inner = outer.type(outer.props);
    expect(inner.props.subTab).toBe('dimension');
    inner.props.onSubTabChange('file');
    expect(props.navigation.handleNavigateReplace).toHaveBeenCalledWith('violations', { _tabKey: 2, subTab: 'file' });
    expect(props.navigation.handleNavigate).not.toHaveBeenCalled();
  });

  it('buildNavigationBundle forwards navStack and navGoTo (the map drill-up dies without them)', () => {
    const navStack = [{ page: 'map' }];
    const navGoTo = vi.fn();
    const bundle = buildNavigationBundle({
      state: { navStack, navGoTo },
      navTab: vi.fn(), navStackLength: 1,
      isEvaluating: false, showToast: vi.fn(), setWizardEntry: vi.fn(),
    });
    expect(bundle.navStack).toBe(navStack);
    expect(bundle.navGoTo).toBe(navGoTo);
  });
});

// Teammate persona, one click deeper than the data pages: with zero LOCAL
// projects, drill-in pages (file/finding/dimension detail...) must not wall
// a shared selection behind the add-a-project tour. Same gate class as the
// DashboardPage/MapPage/HistoryPage/ViolationsPage empty-state fixes.
describe('shouldWallEmptyProjects', () => {
  it('never walls a shared selection, even with zero local projects', () => {
    expect(shouldWallEmptyProjects({ page: 'file', projects: [], selectedSource: 'shared' })).toBe(false);
  });

  it('walls drill-in pages for a local source with zero projects (unchanged)', () => {
    expect(shouldWallEmptyProjects({ page: 'file', projects: [], selectedSource: 'local' })).toBe(true);
  });

  it('never walls the self-handled data tabs', () => {
    expect(shouldWallEmptyProjects({ page: 'overview', projects: [], selectedSource: 'local' })).toBe(false);
  });

  it('never walls the project-free tabs', () => {
    expect(shouldWallEmptyProjects({ page: 'projects', projects: [], selectedSource: 'local' })).toBe(false);
  });

  it('does not wall once local projects exist', () => {
    expect(shouldWallEmptyProjects({ page: 'file', projects: [{ id: 'p1' }], selectedSource: 'local' })).toBe(false);
  });
});

// Pins the session-start effect's payload shape: `source` must reach
// startAssistantSession so remote (shared) projects get read-only sessions
// server-side. Regression: this used to be an inline object literal in the
// effect with no test coverage of the `source` field specifically.
describe('buildAssistantSessionPayload', () => {
  it('passes source through unchanged', () => {
    expect(buildAssistantSessionPayload({ provider: 'p', source: 'shared' }).source).toBe('shared');
  });

  it('includes all five keys', () => {
    const payload = buildAssistantSessionPayload({
      provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1', source: 'local',
    });
    expect(Object.keys(payload).sort()).toEqual(['model', 'projectId', 'provider', 'runId', 'source'].sort());
    expect(payload).toEqual({ provider: 'claude', model: 'sonnet', projectId: 'p1', runId: 'r1', source: 'local' });
  });

  it('leaves an absent source as undefined (API applies its own local default)', () => {
    const payload = buildAssistantSessionPayload({ provider: 'p' });
    expect(payload.source).toBeUndefined();
    expect('source' in payload).toBe(true);
  });
});

// The wizard registers a project on its Repo & Scan step, but the projects
// list in React state is only reloaded at boot and when an evaluation
// finishes. Both wizard exits that leave a registered project behind (saved
// close and launch) must reload the list so the new project appears in the
// Projects tab immediately, before any run exists.
describe('buildWizardHandlers', () => {
  function stubState() {
    return {
      loadProjects: vi.fn(),
      refreshDashboard: vi.fn(),
      evalLifecycle: { handleStartEvaluation: vi.fn() },
    };
  }

  it('onClose after a saved exit reloads the projects list', () => {
    const state = stubState();
    const setWizardEntry = vi.fn();
    const { onClose } = buildWizardHandlers({ state, setWizardEntry, navTab: vi.fn() });
    onClose({ saved: true, projectId: 'proj-1' });
    expect(setWizardEntry).toHaveBeenCalledWith(null);
    expect(state.loadProjects).toHaveBeenCalled();
    expect(state.refreshDashboard).toHaveBeenCalled();
  });

  it('onClose without a saved project does not reload anything', () => {
    const state = stubState();
    const setWizardEntry = vi.fn();
    const { onClose } = buildWizardHandlers({ state, setWizardEntry, navTab: vi.fn() });
    onClose({ saved: false });
    expect(setWizardEntry).toHaveBeenCalledWith(null);
    expect(state.loadProjects).not.toHaveBeenCalled();
    expect(state.refreshDashboard).not.toHaveBeenCalled();
  });

  it('onLaunch reloads the projects list, starts the evaluation, and navigates', () => {
    const state = stubState();
    const navTab = vi.fn();
    const { onLaunch } = buildWizardHandlers({ state, setWizardEntry: vi.fn(), navTab });
    onLaunch({
      projectId: 'proj-1', repo: '/x/repo', scopePath: null, branch: null,
      provider: { id: 'claude', model: 'sonnet' }, standardIds: ['security'], totalTimeLimitS: 60,
    });
    expect(state.loadProjects).toHaveBeenCalled();
    expect(state.evalLifecycle.handleStartEvaluation).toHaveBeenCalledWith(expect.objectContaining({
      repo: '/x/repo', dimensions: ['security'], aiCmd: 'claude', aiModel: 'sonnet', timeLimit: 60,
    }));
    expect(navTab).toHaveBeenCalledWith('evaluate');
  });

  it('onLaunch falls back to the projectId when no repo path is present', () => {
    const state = stubState();
    const { onLaunch } = buildWizardHandlers({ state, setWizardEntry: vi.fn(), navTab: vi.fn() });
    onLaunch({ projectId: 'proj-1', repo: null, provider: {}, standardIds: [] });
    expect(state.evalLifecycle.handleStartEvaluation).toHaveBeenCalledWith(expect.objectContaining({ repo: 'proj-1' }));
  });
});

// Important 4: disconnecting the shared repo in Settings must not strand a
// 'shared' selection pointing at a config that no longer exists.
describe('resolveSelectionAfterSharedDisconnect', () => {
  it('does nothing when the current selection is not shared', () => {
    expect(resolveSelectionAfterSharedDisconnect({ selectedSource: 'local', projects: [{ id: 'p1' }] })).toBeNull();
  });

  it('resets to the first local project when one exists', () => {
    const projects = [{ id: 'p1', name: 'p1' }, { id: 'p2', name: 'p2' }];
    expect(resolveSelectionAfterSharedDisconnect({ selectedSource: 'shared', projects }))
      .toEqual({ id: 'p1', source: 'local' });
  });

  it('clears the selection to the app\'s no-project state when there are no local projects', () => {
    expect(resolveSelectionAfterSharedDisconnect({ selectedSource: 'shared', projects: [] }))
      .toEqual({ id: '', source: 'local' });
  });
});

// Same producer x consumer hazard as buildNavigationBundle, but silent: the
// dashboard bundle is an explicit key whitelist, so a field DashboardPage
// reads arrives as undefined unless it is forwarded. Nothing throws — the
// feature is simply inert, which is exactly how the dimension-panel pending
// state shipped dead the first time.
describe('buildDashboardDataBundle', () => {
  const stubState = () => ({
    selectedProject: 'p1', selectedSource: 'local', selectedRun: 'latest',
    projects: [], projectsLoaded: true,
    dashboard: {}, accumulated: {}, latestAccumulated: {},
    loading: false, isFetching: false, scoresPending: true, error: null,
    sharedProjectInfo: null,
    availableRuns: [], dailyRuns: [], overviewRunIndex: 0,
    selectedDisplayName: 'p1',
    granularity: 'day', onGranularityChange: () => {},
  });

  it('forwards scoresPending (the dimension cards look settled while stale without it)', () => {
    const bundle = buildDashboardDataBundle({ state: stubState(), sharedHasContent: false });
    expect(bundle.scoresPending).toBe(true);
  });

  it('forwards every key DashboardPage destructures off its data prop', () => {
    const bundle = buildDashboardDataBundle({ state: stubState(), sharedHasContent: true });
    // Mirrors the destructure at the top of DashboardPage.
    const consumed = [
      'selectedProject', 'selectedSource', 'selectedRun', 'projects', 'sharedProjectInfo',
      'dashboard', 'accumulated', 'loading', 'isFetching', 'scoresPending', 'error',
      'availableRuns', 'dailyRuns', 'overviewRunIndex', 'granularity',
      'onGranularityChange', 'sharedHasContent',
    ];
    const missing = consumed.filter((k) => !(k in bundle));
    expect(missing).toEqual([]);
  });
});

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
