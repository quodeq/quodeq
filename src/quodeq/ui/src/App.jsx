import { lazy, Suspense, useMemo, useState, useEffect, useRef } from 'react';
import NavBreadcrumb, { labelFor as navLabelFor } from './features/explorer/components/NavBreadcrumb.jsx';
import UpdateBanner from './features/updates/UpdateBanner.jsx';

const DashboardPage = lazy(() => import('./features/dashboard/components/DashboardPage.jsx'));
const ExplorerPage = lazy(() => import('./features/explorer/components/ExplorerPage.jsx'));
const FileDetailPage = lazy(() => import('./features/explorer/components/FileDetailPage.jsx'));
const PrincipleDetailPage = lazy(() => import('./features/explorer/components/PrincipleDetailPage.jsx'));
const FindingDetailPage = lazy(() => import('./features/explorer/components/FindingDetailPage.jsx'));
const ProjectsPage = lazy(() => import('./features/dashboard/components/ProjectsPage.jsx'));
const HistoryPage = lazy(() => import('./features/history/components/HistoryPage.jsx'));
const EvaluateScreen = lazy(() => import('./features/evaluation/components/EvaluateScreen.jsx'));
const SettingsPage = lazy(() => import('./features/settings/components/SettingsPage.jsx'));
const GradeFormulaPage = lazy(() => import('./features/grade-formula/GradeFormulaPage.jsx'));
const StandardsPage = lazy(() => import('./features/standards/StandardsPage.jsx'));
const ViolationsPage = lazy(() => import('./features/violations/components/ViolationsPage.jsx'));
const MapPage = lazy(() => import('./features/map/components/MapPage.jsx'));
const HelpPage = lazy(() => import('./features/help/components/HelpPage.jsx'));
const OnboardingWizard = lazy(() => import('./features/onboarding/components/OnboardingWizard.jsx'));
import EmptyStateWithTour from './features/onboarding/components/EmptyStateWithTour.jsx';
import ServerDisconnectedOverlay from './components/ServerDisconnectedOverlay.jsx';
import { useQueryClient } from '@tanstack/react-query';
import { useApi } from './api/ApiContext.jsx';
import { applyMutationDelta } from './api/applyMutationDelta.js';
import { getGradeFormula } from './api/index.js';
import { setGradeThresholds } from './utils/gradeThresholds.js';
import { deriveEvaluatePreselect } from './utils/evaluatePreselect.js';
import LoadingScreen from './components/LoadingScreen.jsx';
import Sidebar from './components/Sidebar.jsx';
import TopBar from './components/TopBar.jsx';
import { ACTIVE_PROVIDER_KEY, providerKey } from './constants.js';
import ProjectHeader from './components/ProjectHeader.jsx';
import { useAppState, formatDayLabel } from './hooks/useAppState.js';
import { readVisibleStandardIds } from './utils/visibleStandards.js';
import { buildProjectRootFile } from './utils/explorerUtils.js';
import { filterTrendByVisibleStandards, filterAccumulatedByVisibleStandards } from './utils/scoreFiltering.js';
import { syncNativeTitlebar } from './utils/nativeTitlebar.js';
import { SidePane, useSidePane } from './features/side-pane/index.js';
import { VerifiedFindingsProvider } from './features/violations/components/verifiedFindingsContext.jsx';
import { BottomDrawer } from './features/drawer/BottomDrawer.jsx';
import { useAssistantDrawer } from './features/assistant/AssistantDrawerProvider.jsx';
import { useAssistantProvider } from './features/settings/hooks/useAssistantProvider.js';
import { deriveAssistantContext } from './features/assistant/useAssistantContext.js';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { EvalLogProvider } from './features/evaluation/eval-log/EvalLogProvider.jsx';
import { ServerLogProvider } from './features/settings/server-log/ServerLogProvider.jsx';
import { OllamaLogProvider } from './features/settings/ollama-log/OllamaLogProvider.jsx';
import { LlamaCppLogProvider } from './features/settings/llamacpp-log/LlamaCppLogProvider.jsx';

// Tabs that are reachable with zero projects. `projects` is in here so a
// fresh-install user can land on Projects and add their first one without
// hitting the "no analyzed projects yet" wall.
const NO_PROJECT_TABS = ['projects', 'evaluate', 'standards', 'settings', 'help', 'grade-formula'];
const SELF_HANDLED_EMPTY = new Set(['overview', 'map', 'violations', 'history']);

/**
 * Returns whether the app is currently rendering dark, taking the saved
 * theme mode and — when it's 'system' — the OS preference into account.
 * Kept in App so the topbar's theme toggle reflects what's on screen
 * rather than the mode literal.
 */
function useEffectiveDark(themeMode) {
  const [prefersDark, setPrefersDark] = useState(() =>
    typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-color-scheme: dark)').matches
  );
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => setPrefersDark(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);
  if (themeMode === 'dark') return true;
  if (themeMode === 'light') return false;
  return prefersDark;
}

/**
 * Push the on-screen dark/light theme to the native window titlebar
 * whenever it changes, and once more when the pywebview bridge becomes
 * ready (it can inject after first render). No-op in a browser.
 */
function useNativeTitlebarSync(effectiveDark) {
  useEffect(() => {
    syncNativeTitlebar(effectiveDark);
    const onReady = () => syncNativeTitlebar(effectiveDark);
    window.addEventListener('pywebviewready', onReady);
    return () => window.removeEventListener('pywebviewready', onReady);
  }, [effectiveDark]);
}

/**
 * @param {{ serverHealth: Object, evaluation: Object, selectedProject: string, projects: Array, onGoToProjects: Function, onGoToSettings: Function, preselectDims: string[]|undefined }} props
 * @returns {JSX.Element}
 */
function EvaluateCase({ serverHealth, evaluation, selectedProject, projects, onGoToProjects, onGoToSettings, preselectDims }) {
  const { connected, setConnected } = serverHealth;
  const { job, jobError, liveViolations, handleStartEvaluation, handleEvalDismiss, cancelEvaluation, startedProject } = evaluation;
  const projectInfo = projects?.find(p => (p.id || p.name) === selectedProject) || null;
  // The in-progress card describes the running job's own project, which can
  // differ from the UI's global selection. Resolve it the same way so the
  // card label follows the job rather than the selection. Before the
  // report-path marker resolves outputProject, the project the job was
  // started for fills the gap; the global selection is never used.
  const jobProjectInfo = job?.outputProject
    ? (projects?.find(p => (p.id || p.name) === job.outputProject) || null)
    : null;
  const startedProjectInfo = startedProject
    ? (projects?.find(p => (p.id || p.name) === startedProject) || null)
    : null;
  return (
    <>
      {!connected && <ServerDisconnectedOverlay onReconnect={() => setConnected(true)} />}
      <EvaluateScreen
        evaluation={{ job, jobError, liveViolations }}
        context={{ selectedProject, projectInfo, jobProjectInfo, startedProjectInfo, preselectDims }}
        actions={{ onStart: handleStartEvaluation, onDismiss: handleEvalDismiss, onCancel: cancelEvaluation, onGoToProjects, onGoToSettings }}
      />
    </>
  );
}

/**
 * @param {{ settings: Object }} props
 * @returns {JSX.Element}
 */
function SettingsCase({ settings, onOpenGradeFormula }) {
  return (
    <SettingsPage
      theme={{ mode: settings.themeMode, family: settings.themeFamily, onApplyMode: settings.applyMode, onApplyFamily: settings.applyFamily }}
      onOpenGradeFormula={onOpenGradeFormula}
    />
  );
}

function resolveHistorySelectedRunId(selectedRun, trend) {
  if (selectedRun && selectedRun !== 'latest' && trend.some((t) => t.runId === selectedRun)) return selectedRun;
  return trend.length > 0 ? trend[0].runId : null;
}

function buildDismissPayload(v, fallbackDimension) {
  const fileParts = (v.file || '').split(':');
  const file = fileParts[0];
  const line = v.line ?? (fileParts[1] ? parseInt(fileParts[1], 10) : 0);
  return {
    req: v.req || v.principle,
    file,
    line,
    dimension: v.dimension || fallbackDimension || '',
    severity: v.severity,
    title: v.title || '',
    reason: v.reason,
    reqRefs: v.reqRefs || [],
    context: v.context || '',
    snippet: v.snippet || '',
    scope: v.scope || '',
    endLine: v.endLine || 0,
    principle: v.principle || '',
  };
}

function renderEvalPrincipleDetail(params, props) {
  const { selectedProject, selectedRun } = props.navigation;
  const evalPrincipal = {
    ...params.evalPrincipal,
    project: params.evalPrincipal?.project || selectedProject || '',
    runId: params.evalPrincipal?.runId || selectedRun || '',
  };
  return (
    <PrincipleDetailPage
      evalPrincipal={evalPrincipal}
      severityFilter={params.severity || null}
      onDismiss={async (v) => {
        // POST returns { scores: { dimensions, summary } } — the rescored
        // payload for this run. PrincipleDetailPage applies it to its
        // local liveScore/liveGrade. The dashboard refetch covers the
        // accumulated (cross-run) rollup separately.
        const payload = { ...buildDismissPayload(v, evalPrincipal.dimension), run_id: evalPrincipal.runId };
        const result = await props.dismissFinding(selectedProject, payload);
        props.applyDelta?.(selectedProject, result?.scores, result?.delta);
        props.refreshDashboard?.();
        props.bumpDismissRefresh?.();
        return result;
      }}
    />
  );
}

// Exported so unit tests can pin the runId-threading contract without having
// to mount the whole App. Callers from the Violations page must pass the
// dimension's ``fromRunId`` — see ``ViolationsRoute.navigateToPrinciple`` for
// the regression history.
export function buildEvalPrincipal(principleObj, principleGrade, runId) {
  const violations = principleObj.violations || [];
  const compliance = principleObj.compliance || [];
  return {
    principle: principleObj.principle,
    score: principleGrade?.score || null,
    grade: principleGrade?.grade || null,
    dimension: principleObj.dimension || '',
    runId: runId || '',
    principleData: {
      name: principleObj.principle,
      grade: principleGrade?.grade || null,
      violations,
      compliance,
    },
    dimViolations: violations,
    dimCompliance: compliance,
  };
}

function ViolationsRoute({ params, props }) {
  const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
  const dims = acc?.dimensions || [];
  const nav = props.navigation.handleNavigate;

  const dimMap = new Map(dims.map(d => [d.dimension, d]));
  const principleMap = new Map(
    dims.flatMap(d => (d.principles || []).map(p => [`${d.dimension}\0${p.name || p.principle}`, p]))
  );
  function navigateToPrinciple(principleObj, severity) {
    const dim = dimMap.get(principleObj.dimension);
    const pg = principleMap.get(`${principleObj.dimension}\0${principleObj.principle}`);
    // dim.fromRunId is the run whose data populated this accumulated entry;
    // threading it through lets the dismiss POST carry a real run id so the
    // backend can rescore and project the action into SQL — without this the
    // PrincipleDetail score never moves on dismiss and the entry never lands
    // on the Dismissed tab.
    nav('evalprinciple', {
      evalPrincipal: buildEvalPrincipal(principleObj, pg, dim?.fromRunId),
      severity,
      sourceTab: 'violations',
    });
  }

  function navigateToDimension(row, severity) {
    const dim = row.raw || dimMap.get(row.dimension);
    if (!dim) return;
    // Cell clicks on a dimension row (numeric severity columns or the
    // "violations" total) drill into the dimension's findings — match the
    // project/run pattern by handing FileDetailPage a synthetic file
    // aggregated from the dimension, with the chosen severity preselected.
    const dimFile = buildProjectRootFile([dim], dim.dimension);
    const severityFilter = severity || 'all';
    nav('file', {
      file: dimFile,
      severityFilter,
      runId: dim.fromRunId,
      dateLabel: dim.fromDateLabel,
      sourceTab: 'violations',
    });
  }

  return (
    <ViolationsPage
      data={{
        accumulated: acc,
        accumulatedDimensions: dims,
        selectedProject: props.navigation.selectedProject,
        projects: props.navigation.projects,
        projectsLoaded: props.navigation.projectsLoaded,
        projectName: props.dashboardData.selectedDisplayName,
        loading: props.dashboardData.loading,
        isFetching: props.dashboardData.isFetching,
        dismissRefreshKey: props.dismissRefreshKey,
      }}
      callbacks={{
        onDimensionClick: (dim) => nav('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject, sourceTab: 'violations' }),
        onFileClick: (fileObj, opts) => nav('file', { file: fileObj, sourceTab: 'violations', severityFilter: opts?.severity || null }),
        onCellClick: ({ row, severity }) => {
          if (row.type === 'principle' && row.principleObj) {
            navigateToPrinciple(row.principleObj, severity);
          } else {
            navigateToDimension(row, severity);
          }
        },
        onPrincipleClick: (principleObj) => navigateToPrinciple(principleObj),
        onRefresh: props.refreshDashboard,
        onNavigate: nav,
      }}
      isDirectNav={props.navigation.navStackLength === 1}
      tabKey={params._tabKey || 0}
    />
  );
}

const ROUTE_RENDERERS = {
  overview: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate, onRunSelect: props.navigation.handleRunSelect, onProjectsReload: props.navigation.loadProjects }} runMode={false} />,
  violations: (params, props) => <ViolationsRoute params={params} props={props} />,
  map: (params, props) => {
    const acc = props.dashboardData.latestAccumulated || props.dashboardData.accumulated;
    const isDirectNav = props.navigation.navStackLength === 1;
    return <MapPage
      data={{
        accumulated: acc,
        dashboard: props.dashboardData.dashboard,
        projectName: props.dashboardData.selectedDisplayName,
        projects: props.navigation.projects,
        projectsLoaded: props.navigation.projectsLoaded,
        selectedProject: props.navigation.selectedProject,
        loading: props.dashboardData.loading,
        isFetching: props.dashboardData.isFetching,
      }}
      callbacks={{ onNavigate: props.navigation.handleNavigate, onRefresh: props.refreshDashboard }}
      isDirectNav={isDirectNav}
      tabKey={params._tabKey || 0}
    />;
  },
  run: (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate }} runMode={true} />,
  history: (params, props) => {
    const trend = props.dashboardData.dashboard?.trend || [];
    const runs = props.dashboardData.availableRuns || [];
    const idx = props.dashboardData.overviewRunIndex || 0;
    return (
      <HistoryPage
        trend={trend}
        selection={{
          selectedRunId: resolveHistorySelectedRunId(props.navigation.historySelectedRun, trend),
          selectedRunScore: props.dashboardData.accumulated?.summary?.numericAverage,
        }}
        availableRuns={runs}
        dimensions={{
          accumulatedDimensions: props.dashboardData.accumulated?.dimensions || [],
          lastRun: { date: props.dashboardData.accumulated?.dimensions?.[0]?.fromDateLabel, runId: props.dashboardData.accumulated?.dimensions?.[0]?.fromRunId },
        }}
        callbacks={{
          onRunClick: (runId, dateLabel) => props.navigation.handleNavigate('history-run', { runId, dateLabel }),
          onDimensionClick: (dim) => props.navigation.handleNavigate('explorer', { dimension: dim.dimension, runId: dim.fromRunId, dateLabel: dim.fromDateLabel, fromProject: dim.fromProject }),
          onNavigate: props.navigation.handleNavigate,
          onRunChange: props.navigation.setHistorySelectedRun,
          onRunDeleted: () => props.refreshDashboard?.(),
        }}
        projects={props.navigation.projects}
        projectsLoaded={props.navigation.projectsLoaded}
        selectedProject={props.navigation.selectedProject}
        loading={props.dashboardData.loading}
        isFetching={props.dashboardData.isFetching}
        projectInfo={props.navigation.projects?.find((p) => (p.id || p.name) === props.navigation.selectedProject) || null}
      />
    );
  },
  'history-run': (params, props) => <DashboardPage data={props.dashboardData} callbacks={{ onNavigate: props.navigation.handleNavigate }} runMode={true} />,
  explorer: (params, props) => (
    <ExplorerPage
      project={params.fromProject || props.navigation.selectedProject}
      dimension={params.dimension}
      runId={params.runId}
      dateLabel={params.dateLabel}
      onNavigate={props.navigation.handleNavigate}
      refreshSignal={props.dashboardData.dashboard}
      trend={props.dashboardData.dashboard?.trend || []}
      granularity={props.dashboardData.granularity}
      onGranularityChange={props.dashboardData.onGranularityChange}
    />
  ),
  evaluate: (params, props) => <EvaluateCase serverHealth={props.serverHealth} evaluation={props.evaluation} selectedProject={props.navigation.selectedProject} projects={props.navigation.projects} preselectDims={params.preselectDims} onGoToProjects={() => props.navigation.navTab('projects')} onGoToSettings={() => props.navigation.navTab('settings')} />,
  file: (params, props) => (
    <FileDetailPage
      file={params.file}
      runId={params.runId}
      dateLabel={params.dateLabel}
      severityFilter={params.severityFilter || params.severity || null}
      onDismiss={async (v) => {
        const payload = { ...buildDismissPayload(v), run_id: params.runId };
        const result = await props.dismissFinding(props.navigation.selectedProject, payload);
        props.applyDelta?.(props.navigation.selectedProject, result?.scores, result?.delta);
        props.refreshDashboard?.();
        props.bumpDismissRefresh?.();
        return result;
      }}
    />
  ),
  evalprinciple: renderEvalPrincipleDetail,
  'eval-principle-detail': renderEvalPrincipleDetail,
  finding: (params, props) => (
    <FindingDetailPage
      finding={params.finding}
      principle={params.principle}
      dimension={params.dimension}
      onDismiss={async (v) => {
        const payload = { ...buildDismissPayload(v, params.dimension), run_id: params.runId };
        const result = await props.dismissFinding(props.navigation.selectedProject, payload);
        props.applyDelta?.(props.navigation.selectedProject, result?.scores, result?.delta);
        props.refreshDashboard?.();
        props.bumpDismissRefresh?.();
        return result;
      }}
    />
  ),
  settings: (params, props) => <SettingsCase settings={props.settings} onOpenGradeFormula={() => props.navigation.handleNavigate('grade-formula')} />,
  'grade-formula': (params, props) => <GradeFormulaPage navigation={props.navigation} />,
  projects: (params, props) => <ProjectsPage projects={props.navigation.projects} selectedProject={props.navigation.selectedProject} isEvaluating={props.navigation.isEvaluating} actions={{ onSelect: (id) => { props.navigation.handleProjectChange(id); props.navigation.navTab('overview'); }, onDelete: props.navigation.handleDeleteProject, onExport: props.navigation.handleExportProject, onRelocate: props.navigation.handleRelocateProject, onAddProject: props.navigation.onAddProject, onImportProject: props.navigation.onImportProject, onResumeSetup: props.navigation.onResumeSetup }} />,
  standards: () => <StandardsPage />,
  help: () => <HelpPage />,
};

/**
 * @param {{ activePage: { page: string }, props: Object }} params
 * @returns {JSX.Element|null}
 */
function MainContent({ activePage, props }) {
  const { page, ...params } = activePage;
  if (!NO_PROJECT_TABS.includes(page) && !SELF_HANDLED_EMPTY.has(page)) {
    const projects = props.navigation?.projects;
    if (!projects || projects.length === 0) {
      if (!props.navigation?.projectsLoaded) return <LoadingScreen />;
      return (
        <EmptyStateWithTour
          onAdd={() => props.navigation.onAddProject()}
          onTour={() => props.navigation.onTakeTour()}
          isEvaluating={props.navigation.isEvaluating}
        />
      );
    }
  }
  const renderer = ROUTE_RENDERERS[page];
  if (renderer) return renderer(params, props);
  return null;
}

/**
 * @param {{ sidebar: JSX.Element, header: JSX.Element|null, content: JSX.Element }} props
 * @returns {JSX.Element}
 */
function AppShell({ sidebar, header, content, drawer }) {
  return (
    <div className={`app-shell${header ? ' app-shell--with-topbar' : ''}`}>
      {header && <div className="app-shell__topbar">{header}</div>}
      <div className="app-shell__body">
        {sidebar}
        <div className="app-shell__main-column">
          <UpdateBanner />
          <main className="dashboard">
            {content}
          </main>
        </div>
        <SidePane />
        {drawer}
      </div>
    </div>
  );
}

export default function App() {
  const { dismissFinding } = useApi();
  const queryClient = useQueryClient();
  const state = useAppState();
  const APP_VERSION = state.serverVersion;
  const selectedProjectInfo = state.projects?.find((p) => (p.id || p.name) === state.selectedProject) || null;
  const [sidebarPinned, setSidebarPinned] = useState(false);
  const [wizardEntry, setWizardEntry] = useState(null);
  // Incremented after every successful dismiss POST so the violations
  // page's dismissed sub-tab knows to refetch its list. Without this, a
  // dismiss made on the principle / file detail page never appeared in the
  // dismissed list until the user switched projects — the list was only
  // fetched once on mount.
  const [dismissRefreshKey, setDismissRefreshKey] = useState(0);
  const bumpDismissRefresh = () => setDismissRefreshKey((k) => k + 1);
  const { refreshDashboard: refreshDashboardForApply, selectedProject } = state;
  // Shared with the manual dismiss handlers below (buildDismissPayload
  // callers). Patches the dashboard/scores caches from a dismiss response's
  // delta so the Overview updates instantly instead of waiting on a refetch.
  const applyDelta = (project, scores, delta) =>
    applyMutationDelta(queryClient, project, delta && { ...delta, dimensions: scores?.dimensions });
  useEffect(() => {
    const handler = (event) => {
      if (event.detail?.actionType === 'dismiss_finding') {
        // Apply the delta first so the currently-visible screen patches in
        // place immediately; the refresh/refetch below is the lazy,
        // eventual-correctness path (e.g. for views the delta doesn't cover).
        // Prefer the delta's own project over the live selectedProject: the
        // apply POST may resolve after the user switched projects, and the
        // delta is frozen to the action's project. Keying the patch on the
        // live selection would write project A's rollup into project B's cache.
        if (event.detail.delta) {
          try {
            applyDelta(
              event.detail.delta?.project || selectedProject,
              event.detail.scores,
              event.detail.delta,
            );
          } catch {
            // Instant patch is best-effort; the lazy refresh below is the fallback.
          }
        }
        bumpDismissRefresh();
        // Assistant-applied dismissals mutate the same payloads manual ones
        // do; invalidate the project queries so frozen run views (staleTime
        // Infinity) refetch on their next mount instead of showing the
        // pre-dismiss counts forever.
        refreshDashboardForApply?.();
      }
    };
    window.addEventListener('quodeq:assistant-action-applied', handler);
    return () => window.removeEventListener('quodeq:assistant-action-applied', handler);
  }, [refreshDashboardForApply, selectedProject]);
  // Auto-open is a once-per-session decision. Without this guard, closing the
  // wizard sets wizardEntry → null, which re-fires this effect and re-opens
  // the wizard immediately because projects.length is still 0. The user's
  // close action (X, Maybe later, or Start evaluation) is the signal that the
  // auto-open job is done for this page load.
  const autoOpenedRef = useRef(false);

  const { showToast } = useSidePane();

  // Live assistant context: the pure derivation reuses the app-state object
  // we already hold (calling useAssistantContext() would spin up a second
  // useAppState and duplicate every dashboard query). The gate provides the
  // active assistant provider/model.
  const assistantGate = useAssistantProvider();
  const assistantCtx = deriveAssistantContext(state, assistantGate);
  const { isOpen: assistantOpen, activeTab: drawerTab, startSession: startAssistantSession } = useAssistantDrawer();
  const { provider: asstProvider, model: asstModel, projectId: asstProjectId, runId: asstRunId } = assistantCtx;
  // Start (or re-start) the assistant session when the drawer is open and on
  // any provider/model/project/run change while it stays open. startSession
  // dedupes by context key, so re-runs with an unchanged context no-op; a
  // real project/run switch produces a fresh session. We deliberately do NOT
  // start a session while the drawer is closed — sends only originate from the
  // open drawer, so first-open is early enough and avoids needless sessions.
  useEffect(() => {
    if (!assistantOpen || drawerTab !== 'assistant') return;
    startAssistantSession({ provider: asstProvider, model: asstModel, projectId: asstProjectId, runId: asstRunId });
  }, [assistantOpen, drawerTab, asstProvider, asstModel, asstProjectId, asstRunId, startAssistantSession]);

  // Sync the client-side grade-label thresholds with the server formula at
  // boot so every gauge/badge agrees with the applied Q² parameters. The
  // gradeThresholds store seeds with the Q² defaults, so a failed/absent
  // fetch leaves a sane fallback in place.
  useEffect(() => {
    getGradeFormula()
      .then((d) => setGradeThresholds(d?.current?.gradeThresholds))
      .catch(() => {});
  }, []);

  // While an evaluation is running we block any path that would open the
  // onboarding wizard or start a second evaluation — only one job may be in
  // flight at a time.
  const isEvaluating = state.evalLifecycle?.job?.status === 'running';

  // Auto-open wizard on first paint when there are no projects and the user
  // has not explicitly skipped. The skip flag only suppresses auto-open — it
  // never blocks "Add a project" or "Take the tour" buttons.
  useEffect(() => {
    if (autoOpenedRef.current) return;
    if (!state.projectsLoaded) return;
    if (state.projects.length > 0) { autoOpenedRef.current = true; return; }
    if (isEvaluating) return;
    let skipped = false;
    try { skipped = localStorage.getItem('quodeq_onboarding_skipped') === 'true'; } catch { /* ignore */ }
    autoOpenedRef.current = true;
    if (!skipped) {
      setWizardEntry({ startStep: 'welcome', isFirstProject: true });
    }
  }, [state.projectsLoaded, state.projects.length, isEvaluating]);

  // Project-data tabs (overview/violations/map/history) only make sense once
  // the selected project has at least one completed evaluation run. Until
  // then, hide them from the sidebar and bounce the user to Evaluate if a
  // cached activeTab lands them on a now-hidden tab. The guards below wait
  // for /api/projects to resolve and for selectedProjectInfo to populate so
  // the bouncer doesn't fire against the transient "no projects loaded yet"
  // state on first paint and strand the user on Evaluate.
  const PROJECT_DATA_TABS = ['overview', 'violations', 'map', 'history'];
  const hasCurrentProjectRuns = (selectedProjectInfo?.runsCount ?? 0) > 0;
  useEffect(() => {
    if (!state.projectsLoaded) return;
    if (state.projects.length === 0) return;
    if (!selectedProjectInfo) return;
    if (!hasCurrentProjectRuns && PROJECT_DATA_TABS.includes(state.activeTab)) {
      state.navTab('evaluate');
    }
  }, [state.projectsLoaded, state.projects.length, selectedProjectInfo, hasCurrentProjectRuns, state.activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const sidebarProvider = (typeof localStorage !== 'undefined' && localStorage.getItem(ACTIVE_PROVIDER_KEY)) || null;
  const sidebarModel = sidebarProvider && typeof localStorage !== 'undefined'
    ? localStorage.getItem(providerKey(sidebarProvider, 'model'))
    : null;
  const { activePage, navStack, navPop, navGoTo, navTab, activeTab } = state;

  // Reset scroll on project switch — useNavStack handles the same for
  // tab/page changes, but selectedProject lives outside the nav stack.
  // Without this, switching from a project scrolled deep into Projects
  // lands the user partway down the next project's Overview.
  useEffect(() => {
    const main = document.querySelector('.app-shell__main-column > .dashboard');
    if (main) main.scrollTop = 0;
  }, [state.selectedProject]);

  const currentDayLabel = useMemo(
    () => formatDayLabel(state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex),
    [state.dashboard?.trend, state.currentOverviewRun, state.dailyRuns, state.overviewRunIndex]
  );

  // Resolve whether the UI is currently rendering dark. Used by the
  // topbar's moon/sun toggle so the icon reflects what's on-screen,
  // not just the saved mode preference.
  const effectiveDark = useEffectiveDark(state.settings.themeMode);
  useNativeTitlebarSync(effectiveDark);
  const toggleTheme = () => {
    state.settings.applyMode(effectiveDark ? 'light' : 'dark');
  };

  // Sidebar counts should respect the user's currently-visible standards so
  // they match the numbers shown on the Violations and History pages.
  const visibleSet = useMemo(() => new Set(readVisibleStandardIds()), []);
  const filteredTrend = useMemo(
    () => filterTrendByVisibleStandards(state.dashboard?.trend || [], visibleSet),
    [state.dashboard?.trend, visibleSet]
  );
  const filteredAccumulated = useMemo(
    () => filterAccumulatedByVisibleStandards(state.accumulated, visibleSet, filteredTrend, null),
    [state.accumulated, visibleSet, filteredTrend]
  );

  const contentProps = {
    dashboardData: {
      selectedProject: state.selectedProject, selectedSource: state.selectedSource, selectedRun: state.selectedRun, projects: state.projects,
      projectsLoaded: state.projectsLoaded,
      dashboard: state.dashboard, accumulated: state.accumulated, latestAccumulated: state.latestAccumulated, loading: state.loading, isFetching: state.isFetching, error: state.error,
      availableRuns: state.availableRuns, dailyRuns: state.dailyRuns, overviewRunIndex: state.overviewRunIndex,
      selectedDisplayName: state.selectedDisplayName,
      granularity: state.granularity, onGranularityChange: state.onGranularityChange,
    },
    navigation: {
      selectedProject: state.selectedProject, selectedSource: state.selectedSource, selectedRun: state.selectedRun, projects: state.projects,
      projectsLoaded: state.projectsLoaded,
      loadProjects: state.loadProjects,
      handleNavigate: state.handleNavigate, handleRunSelect: state.handleRunSelect,
      handleProjectChange: state.handleProjectChange, navTab, navStackLength: navStack.length,
      handleDeleteProject: state.handleDeleteProject, handleExportProject: state.handleExportProject, handleRelocateProject: state.handleRelocateProject, handleImportProject: state.handleImportProject,
      historySelectedRun: state.historySelectedRun, setHistorySelectedRun: state.setHistorySelectedRun,
      currentOverviewRun: state.currentOverviewRun, handleRunPrev: state.handleRunPrev, handleRunNext: state.handleRunNext, handleRunLatest: state.handleRunLatest,
      prefetchHandlers: state.prefetchHandlers,
      onAddProject: () => {
        if (isEvaluating) {
          showToast('An evaluation is in progress. Cancel it before adding a project.');
          return;
        }
        setWizardEntry({ startStep: 'repo-scan', isFirstProject: state.projects.length === 0 });
      },
      onImportProject: () => {
        if (isEvaluating) {
          showToast('An evaluation is in progress. Cancel it before importing a project.');
          return;
        }
        state.handleImportProject();
      },
      onTakeTour: () => {
        if (isEvaluating) {
          showToast('An evaluation is in progress. Cancel it before starting the tour.');
          return;
        }
        setWizardEntry({ startStep: 'welcome', isFirstProject: true });
      },
      onResumeSetup: (projectId) => {
        if (isEvaluating) {
          showToast('An evaluation is in progress. Cancel it before resuming setup.');
          return;
        }
        setWizardEntry({
          startStep: 'provider',
          isFirstProject: false,
          presetProjectId: projectId,
        });
      },
      isEvaluating,
    },
    evaluation: state.evalLifecycle,
    serverHealth: { connected: state.serverConnected, setConnected: state.setServerConnected },
    settings: state.settings,
    refreshDashboard: state.refreshDashboard,
    dismissFinding,
    // Patch the dashboard/scores caches from the dismiss response delta so the
    // Overview updates instantly. Additive — the refreshDashboard /
    // bumpDismissRefresh mechanisms below still run. The delta carries only the
    // mutation shape; the caller folds in the rescored dims from result.scores.
    applyDelta,
    bumpDismissRefresh,
    dismissRefreshKey,
  };

  // Resolve the project's friendly name. Until the /api/projects response
  // has populated the projects array, selectedDisplayName falls back to the
  // raw project id (a UUID) — we explicitly filter that case out so the
  // sidebar and topbar show nothing rather than flashing the UUID.
  const resolvedDisplayName =
    selectedProjectInfo?.displayName
    || selectedProjectInfo?.name
    || (state.selectedDisplayName && state.selectedDisplayName !== state.selectedProject
          ? state.selectedDisplayName
          : null);

  return (
    <>
      <EvalLogProvider>
        <ServerLogProvider>
          <OllamaLogProvider>
            <LlamaCppLogProvider>
              <VerifiedFindingsProvider project={state.selectedProject}>
              <AppShell
          drawer={<BottomDrawer uiState={assistantCtx.uiState} />}
          sidebar={
            <Sidebar
              activeTab={activeTab}
              onNavTab={navTab}
              hasEvaluations={state.projects.length > 0}
              showProjectTabs={hasCurrentProjectRuns}
              projectInfo={{
                displayName: resolvedDisplayName,
                meta: state.headerMeta,
              }}
              version={APP_VERSION}
              violationsCount={filteredAccumulated?.summary?.totalViolations ?? state.accumulated?.summary?.totalViolations ?? null}
              historyCount={filteredTrend.length || state.dashboard?.trend?.length || null}
              lastEvalAt={state.accumulated?.summary?.lastEvaluatedAt || state.accumulated?.summary?.createdAt || null}
              isPinned={sidebarPinned}
              onPinChange={setSidebarPinned}
            />
          }
          header={
            <TopBar
              projectName={resolvedDisplayName}
              activeTab={activeTab}
              serverConnected={state.serverConnected}
              serverUrl={typeof window !== 'undefined' ? window.location.origin : null}
              provider={sidebarProvider}
              model={sidebarModel}
              onEvaluate={state.projects?.length > 0 ? (() => navTab('evaluate', { preselectDims: deriveEvaluatePreselect(activePage) })) : null}
              evaluating={state.evalLifecycle?.job?.status === 'running'}
              onProviderClick={() => navTab('settings')}
              onMenuToggle={() => setSidebarPinned((v) => !v)}
              onSelectProject={() => navTab('projects')}
              breadcrumb={
                <NavBreadcrumb
                  stack={navStack}
                  onGoTo={navGoTo}
                  projectName={resolvedDisplayName}
                  onSelectProject={() => navTab('projects')}
                />
              }
              mobileTitle={navStack.length ? navLabelFor(navStack[navStack.length - 1]) : (activeTab || '')}
              canGoBack={navStack.length > 1}
              onBack={navPop}
              effectiveDark={effectiveDark}
              onToggleTheme={toggleTheme}
            />
          }
          content={
            <Suspense fallback={<LoadingScreen />}>
              <div className="tab-fade" key={activeTab}>
                <MainContent activePage={activePage} props={contentProps} />
              </div>
              {wizardEntry && (
                <OnboardingWizard
                  entry={wizardEntry}
                  onClose={({ saved, projectId }) => {
                    setWizardEntry(null);
                    if (saved && projectId) {
                      state.refreshDashboard?.();
                    }
                  }}
                  onLaunch={({ projectId, repo, scopePath, branch, provider, standardIds, totalTimeLimitS }) => {
                    setWizardEntry(null);
                    const payload = {
                      repo: repo || projectId,
                      dimensions: standardIds,
                    };
                    if (scopePath) payload.scopePath = scopePath;
                    if (branch) payload.branch = branch;
                    if (provider?.id) payload.aiCmd = provider.id;
                    if (provider?.model) payload.aiModel = provider.model;
                    if (totalTimeLimitS) payload.timeLimit = totalTimeLimitS;
                    state.evalLifecycle.handleStartEvaluation(payload);
                    navTab('evaluate');
                  }}
                />
              )}
            </Suspense>
          }
            />
              </VerifiedFindingsProvider>
            </LlamaCppLogProvider>
          </OllamaLogProvider>
        </ServerLogProvider>
      </EvalLogProvider>
    {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </>
  );
}
