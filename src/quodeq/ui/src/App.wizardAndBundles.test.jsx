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

// Split from App.test.jsx: shouldWallEmptyProjects,
// buildAssistantSessionPayload, buildWizardHandlers,
// resolveSelectionAfterSharedDisconnect, and buildDashboardDataBundle.

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
