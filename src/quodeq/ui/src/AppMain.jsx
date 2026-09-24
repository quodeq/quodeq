import { lazy, Suspense } from 'react';
import NavBreadcrumb, { labelFor as navLabelFor } from './features/explorer/components/NavBreadcrumb.jsx';
import UpdateBanner from './features/updates/UpdateBanner.jsx';
import ServerDisconnectedOverlay from './components/ServerDisconnectedOverlay.jsx';
import { deriveEvaluatePreselect } from './utils/evaluatePreselect.js';
import LoadingScreen, { FadingLoadingScreen } from './components/LoadingScreen.jsx';
import Sidebar from './components/Sidebar.jsx';
import TopBar from './components/TopBar.jsx';
import { SidePane } from './features/side-pane/index.js';
import { VerifiedFindingsProvider } from './features/violations/components/verifiedFindingsContext.jsx';
import { BottomDrawer } from './features/drawer/BottomDrawer.jsx';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { EvalLogProvider } from './features/evaluation/eval-log/EvalLogProvider.jsx';
import { ServerLogProvider } from './features/settings/server-log/ServerLogProvider.jsx';
import { OllamaLogProvider } from './features/settings/ollama-log/OllamaLogProvider.jsx';
import { LlamaCppLogProvider } from './features/settings/llamacpp-log/LlamaCppLogProvider.jsx';
import { RescoreTrackerProvider } from './features/grade-formula/rescore/RescoreTrackerProvider.jsx';
import { MainContent } from './routes/renderers.jsx';
import { buildSidebarProps, buildTopBarProps } from './appShellProps.js';
import { JOB_STATUS } from './vocab/jobStatus.js';

const OnboardingWizard = lazy(() => import('./features/onboarding/components/OnboardingWizard.jsx'));

/**
 * @param {{ sidebar: JSX.Element, header: JSX.Element|null, content: JSX.Element,
 *   startupLoader: JSX.Element|null, booting: boolean }} props
 * @returns {JSX.Element}
 */
function AppShell({ sidebar, header, content, drawer, navPending, startupLoader, booting }) {
  return (
    <div className={`app-shell${header ? ' app-shell--with-topbar' : ''}`}>
      {header && <div className="app-shell__topbar">{header}</div>}
      <div className="app-shell__body">
        {sidebar}
        <div className="app-shell__main-column" inert={booting || undefined}>
          {/* Feedback while a navigation's target page renders (useNavStack
              transition). Must live HERE, outside the scrolling <main>: the
              .dashboard is position:relative, so an absolutely-positioned bar
              inside it anchors to the top of the scrollable CONTENT and
              scrolls out of view — exactly where every detail-page card
              lives, so the one navigation that needed feedback never got it. */}
          {navPending && <div className="nav-pending-bar" aria-hidden="true" />}
          <UpdateBanner />
          <main className="dashboard">
            {content}
          </main>
        </div>
        <SidePane />
        {drawer}
        {/* Last child of the body row, NOT of the main column: the column sets
            `contain: layout paint`, which makes it the containing block for
            fixed-position descendants, so a loader mounted inside it was
            clipped to the column and left the sidebar both visible and
            clickable. Out here it covers sidebar + main + side pane and stops
            below the TopBar (see .loading-screen--shell). */}
        {startupLoader}
      </div>
    </div>
  );
}

function AppSidebar({ shell }) {
  const { state, activeTab, navTab, hasCurrentProjectRuns, sharedSignal, resolvedDisplayName, APP_VERSION, sidebarCounts, sidebarPinned, setSidebarPinned, showStartupLoader } = shell;
  return (
    <Sidebar
      inert={showStartupLoader || undefined}
      {...buildSidebarProps({
        activeTab,
        navTab,
        selectedSource: state.selectedSource,
        hasCurrentProjectRuns,
        sharedProjectInfo: state.sharedProjectInfo,
        projects: state.projects,
        sharedHasContent: sharedSignal.hasContent,
        resolvedDisplayName,
        headerMeta: state.headerMeta,
        version: APP_VERSION,
        sidebarCounts,
        lastEvalAt: state.accumulated?.summary?.lastEvaluatedAt || state.accumulated?.summary?.createdAt || null,
        isPinned: sidebarPinned,
        onPinChange: setSidebarPinned,
      })}
    />
  );
}

function AppTopBar({ shell }) {
  const {
    state, activeTab, navTab, resolvedDisplayName, sidebarProvider, sidebarModel, topbarRunProgress,
    activePage, navStack, navGoTo, navPop, breadcrumbSiblingsFor, effectiveDark, toggleTheme, setSidebarPinned,
  } = shell;
  return (
    <TopBar
      {...buildTopBarProps({
        resolvedDisplayName,
        serverConnected: state.serverConnected,
        sidebarProvider,
        sidebarModel,
        selectedSource: state.selectedSource,
        projectsCount: state.projects?.length,
        onEvaluateClick: () => navTab('evaluate', { preselectDims: deriveEvaluatePreselect(activePage) }),
        evaluating: state.evalLifecycle?.job?.status === JOB_STATUS.RUNNING,
        topbarRunProgress,
        navTab,
        setSidebarPinned,
        breadcrumb: (
          <NavBreadcrumb
            stack={navStack}
            onGoTo={navGoTo}
            projectName={resolvedDisplayName}
            onSelectProject={() => navTab('projects')}
            siblingsFor={breadcrumbSiblingsFor}
          />
        ),
        mobileTitle: navStack.length ? navLabelFor(navStack[navStack.length - 1]) : (activeTab || ''),
        navStackLength: navStack.length,
        navPop,
        effectiveDark,
        toggleTheme,
      })}
    />
  );
}

function AppRouteContent({ shell }) {
  const { state, activePage, activeTab, contentProps, wizardEntry, wizardHandlers } = shell;
  return (
    <Suspense fallback={<LoadingScreen />}>
      {/* Every route, not just Evaluate. A dead backend is the one
          failure no page can render around: the Overview's own wall
          falls back to a bare loading spinner that never resolves, so
          a killed server read as "quodeq won't start" with nothing
          on screen to say why or to retry from. */}
      {!state.serverConnected && (
        <ServerDisconnectedOverlay onReconnect={() => state.setServerConnected(true)} />
      )}
      <div className="tab-fade" key={activeTab}>
        <MainContent activePage={activePage} props={contentProps} />
      </div>
      {wizardEntry && (
        <OnboardingWizard
          entry={wizardEntry}
          {...wizardHandlers}
        />
      )}
    </Suspense>
  );
}

// ---------------------------------------------------------------------------
// AppMain — the app shell's render tree (providers, sidebar, topbar, routed
// content). Extracted out of App.jsx (which keeps all state/effects/hooks)
// so App.jsx stays under the file-size cap; this component holds no hooks of
// its own, so App.jsx's hook order/effect timing is unaffected by the move.
// `shell` bundles the already-computed values App.jsx's render used to close
// over inline — same values, same order, no logic change.
// ---------------------------------------------------------------------------
export default function AppMain({ shell }) {
  const { state, navTab, assistantCtx, resolvedDisplayName } = shell;
  return (
    <>
      <EvalLogProvider>
        <ServerLogProvider>
          <OllamaLogProvider>
            <LlamaCppLogProvider>
              <VerifiedFindingsProvider project={state.selectedProject} source={state.selectedSource}>
                {/* Above every page: a grade-formula rescore keeps polling and
                    drops the stale score caches after the user leaves the page. */}
                <RescoreTrackerProvider>
                  <AppShell
                    navPending={state.navPending}
                    booting={shell.showStartupLoader}
                    drawer={<BottomDrawer uiState={assistantCtx.uiState} projectName={resolvedDisplayName}
                      onOpenSettings={() => navTab('settings')} />}
                    sidebar={<AppSidebar shell={shell} />}
                    header={<AppTopBar shell={shell} />}
                    content={<AppRouteContent shell={shell} />}
                    startupLoader={
                      /* One stable mount for the startup loader, OUTSIDE the
                         routed Suspense: inside it, a lazy chunk's suspension
                         unmounts the loader itself and the plain fallback
                         restarts the fade and tips from zero (a loader-to-loader
                         flash). Out here it covers chunk loads AND holds through
                         the Overview's first data (shouldShowStartupLoader), so
                         boot goes loader -> content with no skeleton in
                         between. */
                      <FadingLoadingScreen show={shell.showStartupLoader} variant="shell" tips />
                    }
                  />
                </RescoreTrackerProvider>
              </VerifiedFindingsProvider>
            </LlamaCppLogProvider>
          </OllamaLogProvider>
        </ServerLogProvider>
      </EvalLogProvider>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </>
  );
}
