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

// Split from App.test.jsx: resolveProjectDisplayName,
// buildNavigationBundle, and the map/violations nav-stack view-state
// wiring.

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
