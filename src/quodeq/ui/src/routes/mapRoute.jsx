/**
 * The Map tab's route renderer, moved out of routes/renderers.jsx verbatim
 * (move-only refactor).
 */
import { lazy } from 'react';
import { NAV_TAB } from '../vocab/navTab.js';

const MapPage = lazy(() => import('../features/map/components/MapPage.jsx'));

// The entry we unwind to keeps its own path and _tabKey but takes the
// toggles on screen NOW: the viz style and modes are a display preference,
// not a fact about that level. Restoring the entry as pushed flipped the
// view back to the style it was drilled under (circle pack -> galaxy ->
// climb up -> circle pack again). A default (undefined) toggle drops the
// key rather than stamping undefined into history state.
function withCurrentView(entry, { vizStyle, viewMode, galaxyMode }) {
  const next = { ...entry, vizStyle, viewMode, galaxyMode };
  return Object.fromEntries(Object.entries(next).filter(([, v]) => v !== undefined));
}

export function mapRoute(params, props) {
  const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
  const isDirectNav = props.navigation.navStackLength === 1;
  // The viz drill-down is a real nav-stack entry: drilling into a folder
  // pushes (browser back climbs back out), and navigating up to a path
  // that already sits in the trailing run of map entries unwinds history
  // to it instead of stacking a duplicate -- via navSwapAt, so the target
  // entry is re-stamped with the current toggles (see withCurrentView).
  // Mode/style toggles replace in place so flipping them never grows
  // history. Params are spread forward on every hop so _tabKey (the
  // fresh-tab-click reset signal) survives.
  const handlePathChange = (path) => {
    const current = params.path || '';
    if (path === current) return;
    const stack = props.navigation.navStack || [];
    for (let i = stack.length - 2; i >= 0 && stack[i].page === NAV_TAB.MAP; i--) {
      if ((stack[i].path || '') === path) {
        props.navigation.navSwapAt(i, withCurrentView(stack[i], params));
        return;
      }
    }
    props.navigation.handleNavigate(NAV_TAB.MAP, { ...params, path });
  };
  const replaceView = (patch) => props.navigation.handleNavigateReplace(NAV_TAB.MAP, { ...params, ...patch });
  return <MapPage
    data={{
      accumulated: acc,
      dashboard: props.dashboardData.dashboard,
      projectName: props.dashboardData.selectedDisplayName,
      projects: props.navigation.projects,
      projectsLoaded: props.navigation.projectsLoaded,
      selectedProject: props.navigation.selectedProject,
      selectedSource: props.navigation.selectedSource,
      loading: props.dashboardData.loading,
      isFetching: props.dashboardData.isFetching,
      error: props.dashboardData.error,
    }}
    callbacks={{ onNavigate: props.navigation.handleNavigate, onRetry: props.dashboardData.onRetry }}
    nav={{
      path: params.path || '',
      vizStyle: params.vizStyle,
      viewMode: params.viewMode,
      galaxyMode: params.galaxyMode,
      onPathChange: handlePathChange,
      onVizStyleChange: (v) => replaceView({ vizStyle: v }),
      onViewModeChange: (v) => replaceView({ viewMode: v }),
      onGalaxyModeChange: (v) => replaceView({ galaxyMode: v }),
    }}
    isDirectNav={isDirectNav}
    tabKey={params._tabKey || 0}
  />;
}
