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

// Split from App.test.jsx: buildEvalPrincipal, source-gating helpers
// (isSharedSource/shouldShowEvaluateButton/shouldBounceToEvaluate), and
// the dismiss route-renderer wiring (ROUTE_RENDERERS onDismiss +
// ViolationsRoute onRefresh/onReconcile).

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
