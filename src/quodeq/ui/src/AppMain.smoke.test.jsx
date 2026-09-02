import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import AppMain from './AppMain.jsx';
import { withQueryClient } from './test-utils/withQueryClient.jsx';
import { ApiProvider } from './api/ApiContext.jsx';
import { SidePaneProvider } from './features/side-pane/index.js';
import { AssistantDrawerProvider } from './features/assistant/AssistantDrawerProvider.jsx';

// Closes the coverage hole this class of bug slipped through: App.jsx's
// render tree was extracted into AppMain.jsx (Task 24.5b), and a prop
// builder (buildTopBarProps) dropped a rename along the way -- a bare
// `onToggleTheme,` object-literal shorthand with no `onToggleTheme` binding
// in scope, instead of `onToggleTheme: toggleTheme,`. Nothing in the repo
// previously mounted <App/> or <AppMain/>, so the ReferenceError this throws
// (at buildTopBarProps() call time, before TopBar ever renders) had no test
// to catch it. This test mounts the real AppShell/TopBar render path (with
// unrelated heavy subsystems -- the routed page content and the assistant/
// terminal bottom drawer -- stubbed out, since they are not what's under
// test) and clicks the real theme-toggle button end to end.
vi.mock('./features/drawer/BottomDrawer.jsx', () => ({ BottomDrawer: () => null }));
vi.mock('./routes/renderers.jsx', () => ({ MainContent: () => null }));
vi.mock('./api/assistant.js', () => ({
  createAssistantSession: vi.fn(async () => ({ sessionId: 's1' })),
  postAssistantMessage: vi.fn(async () => ({ accepted: true })),
  stopAssistantTurn: vi.fn(async () => ({ stopping: true })),
  fetchAssistantWorkspace: vi.fn(async () => ({ worktree: null })),
  applyAssistantAction: vi.fn(async () => ({ applied: true })),
  rejectAssistantAction: vi.fn(async () => ({ rejected: true })),
  assistantEventsUrl: (id, a) => `/api/assistant/sessions/${id}/events?after=${a}`,
  fetchAssistantCatalog: vi.fn(async () => ({ commands: [], skills: [], actions: [] })),
}));
vi.mock('./features/assistant/useAssistantStream.js', () => ({
  useAssistantStream: () => ({ messages: [], streaming: false, error: null, reset: vi.fn() }),
}));

function makeFakeApi() {
  return {
    getLlamacppLogAvailable: vi.fn(async () => ({ available: false })),
    getUpdateStatus: vi.fn(async () => ({ available: false })),
  };
}

function makeShell(overrides = {}) {
  return {
    state: {
      selectedProject: null,
      selectedSource: 'local',
      navPending: false,
      sharedProjectInfo: null,
      projects: [],
      headerMeta: null,
      accumulated: null,
      serverConnected: true,
      setServerConnected: () => {},
      evalLifecycle: {},
      warmup: null,
    },
    navTab: () => {},
    activeTab: 'overview',
    activePage: { page: '__smoke_test_unmatched_page__' },
    hasCurrentProjectRuns: false,
    sharedSignal: { hasContent: false },
    assistantCtx: { uiState: {} },
    resolvedDisplayName: 'Smoke Test Project',
    APP_VERSION: '0.0.0-test',
    sidebarCounts: { violationsCount: 0, historyCount: 0 },
    sidebarPinned: false,
    setSidebarPinned: () => {},
    sidebarProvider: 'claude',
    sidebarModel: 'sonnet',
    topbarRunProgress: null,
    navStack: [],
    navGoTo: () => {},
    navPop: () => {},
    breadcrumbSiblingsFor: () => [],
    effectiveDark: false,
    toggleTheme: () => {},
    showStartupLoader: false,
    contentProps: { navigation: { projects: [], selectedSource: 'local', projectsLoaded: true } },
    wizardEntry: null,
    wizardHandlers: {},
    ...overrides,
  };
}

function renderAppMain(shell) {
  const QC = withQueryClient();
  return render(
    <QC>
      <ApiProvider value={makeFakeApi()}>
        <SidePaneProvider>
          <AssistantDrawerProvider>
            <AppMain shell={shell} />
          </AssistantDrawerProvider>
        </SidePaneProvider>
      </ApiProvider>
    </QC>
  );
}

describe('AppMain mount smoke test', () => {
  it('renders the topbar and wires the theme toggle button to shell.toggleTheme', () => {
    const toggleTheme = vi.fn();
    renderAppMain(makeShell({ toggleTheme }));

    const btn = screen.getByRole('button', { name: 'Switch to dark theme' });
    fireEvent.click(btn);

    expect(toggleTheme).toHaveBeenCalledTimes(1);
  });
});
