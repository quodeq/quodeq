import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {
  buildEvalPrincipal, ROUTE_RENDERERS, isSharedSource, shouldBounceToEvaluate, shouldShowEvaluateButton,
  resolveSelectionAfterSharedDisconnect, shouldAutoOpenOnboardingWizard, shouldShowProjectTabs,
  buildNavigationBundle, shouldWallEmptyProjects, buildWizardHandlers, buildAssistantSessionPayload,
  resolveProjectDisplayName,
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
      dismissFinding: vi.fn(),
      applyDelta: vi.fn(),
      refreshDashboard: vi.fn(),
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
