import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { AssistantDrawerProvider, useAssistantDrawer } from './AssistantDrawerProvider.jsx';

// Split from AssistantDrawerProvider.test.jsx: the Ctrl+`/Ctrl+Shift+`
// shortcuts, tab switching, panel open/close, the catalog fetch/cache, and
// addLocalExchange. The full mock header + Probe harness are duplicated
// here (vi.mock hoisting is file-scoped).

vi.mock('../../api/assistant.js', () => ({
  createAssistantSession: vi.fn(async (payload) => ({ sessionId: 's1', readOnly: payload?.source === 'shared' })),
  postAssistantMessage: vi.fn(async () => ({ accepted: true })),
  stopAssistantTurn: vi.fn(async () => ({ stopping: true })),
  fetchAssistantWorkspace: vi.fn(async () => ({ worktree: null })),
  applyAssistantAction: vi.fn(async () => ({ applied: true })),
  rejectAssistantAction: vi.fn(async () => ({ rejected: true })),
  assistantEventsUrl: (id, a) => `/api/assistant/sessions/${id}/events?after=${a}`,
  fetchAssistantCatalog: vi.fn(async () => ({ commands: [], skills: [], actions: [] })),
}));
vi.mock('./useAssistantStream.js', () => ({
  useAssistantStream: () => ({ messages: [], streaming: false, error: null, reset: vi.fn() }),
}));
import { fetchAssistantCatalog } from '../../api/assistant.js';

function Probe() {
  const d = useAssistantDrawer();
  return (
    <div>
      <span data-testid="open">{String(d.isOpen)}</span>
      <span data-testid="streaming">{String(d.streaming)}</span>
      <span data-testid="provider">{String(d.provider)}</span>
      <span data-testid="model">{String(d.model)}</span>
      <span data-testid="error">{String(d.error)}</span>
      <span data-testid="web">{String(d.webEnabled)}</span>
      <span data-testid="catalog">{JSON.stringify(d.catalog)}</span>
      <span data-testid="messages">{JSON.stringify(d.messages)}</span>
      <span data-testid="panels">{JSON.stringify(d.openPanels)}</span>
      <span data-testid="active">{d.activeTab}</span>
      <span data-testid="readonly">{String(d.readOnly)}</span>
      <button onClick={d.toggleWebEnabled}>web</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' })}>start</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pA', runId: 'r' })}>startA</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pB', runId: 'r' })}>startB</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r', source: 'shared' })}>startShared</button>
      <button onClick={d.toggle}>toggle</button>
      <button onClick={() => d.openTab('assistant')}>openAssistant</button>
      <button onClick={() => d.openTab('terminal')}>openTerminal</button>
      <button onClick={() => d.closePanel('assistant')}>closeAssistantPanel</button>
      <button onClick={() => d.sendMessage('hi', { activeTab: 'overview' })}>send</button>
      <button onClick={d.stopTurn}>stop</button>
      <button onClick={d.resetConversation}>reset</button>
      <button onClick={() => d.addLocalExchange?.('/help', 'HELP TEXT')}>localExchange</button>
    </div>
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => localStorage.clear());

describe('Ctrl+` shortcut', () => {
  // Shared projects get read-only sessions server-side: the backend roots
  // reads in the shared clone and registers no mutating tools, so the
  // shortcut opens the drawer for any persisted source.
  const fireCtrlBacktick = () => {
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Backquote', ctrlKey: true, cancelable: true }));
  };
  const fireCtrlShiftBacktick = () => {
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Backquote', ctrlKey: true, shiftKey: true, cancelable: true }));
  };

  it('Ctrl+` opens the assistant even when the persisted source is shared (read-only sessions handle safety)', () => {
    localStorage.setItem('quodeq_selected_source', 'shared');
    render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
    act(() => fireCtrlBacktick());
    expect(screen.getByTestId('open').textContent).toBe('true');
  });

  it('opens the drawer when the persisted source is local', () => {
    localStorage.setItem('quodeq_selected_source', 'local');
    render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
    act(() => fireCtrlBacktick());
    expect(screen.getByTestId('open').textContent).toBe('true');
  });

  it('opens the drawer when no source is persisted (defaults to local)', () => {
    render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
    act(() => fireCtrlBacktick());
    expect(screen.getByTestId('open').textContent).toBe('true');
  });

  it('terminal shortcut (Ctrl+Shift+`) opens terminal for shared projects', () => {
    localStorage.setItem('quodeq_selected_source', 'shared');
    localStorage.setItem('cc-assistant-enabled', 'true');
    localStorage.setItem('cc-terminal-enabled', 'true');
    render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
    act(() => fireCtrlShiftBacktick());
    expect(screen.getByTestId('open').textContent).toBe('true');
  });

  it('terminal shortcut (Ctrl+Shift+`) opens terminal for local projects', () => {
    localStorage.setItem('quodeq_selected_source', 'local');
    localStorage.setItem('cc-assistant-enabled', 'true');
    localStorage.setItem('cc-terminal-enabled', 'true');
    render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
    act(() => fireCtrlShiftBacktick());
    expect(screen.getByTestId('open').textContent).toBe('true');
  });
});

it('exposes activeTab defaulting to assistant; openTab switches the active tab', () => {
  // Both features enabled so the per-tab disable-fallback effect doesn't
  // reroute the initial tab.
  localStorage.setItem('cc-assistant-enabled', 'true');
  localStorage.setItem('cc-terminal-enabled', 'true');
  let hookRef;
  const Grab = () => { hookRef = useAssistantDrawer(); return null; };
  render(<AssistantDrawerProvider><Grab /></AssistantDrawerProvider>);
  expect(hookRef.activeTab).toBe('assistant');
  act(() => hookRef.openTab('terminal'));
  expect(hookRef.activeTab).toBe('terminal');
});

it('fetches the catalog once when the drawer opens, cached across open/close/open', async () => {
  fetchAssistantCatalog.mockResolvedValue({ commands: [], skills: [], actions: [] });
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);

  // Drawer is closed; catalog should be null and fetch should not have been called.
  expect(screen.getByTestId('catalog').textContent).toBe('null');
  expect(fetchAssistantCatalog).not.toHaveBeenCalled();

  // Open the assistant panel.
  await act(async () => { screen.getByText('openAssistant').click(); });
  expect(fetchAssistantCatalog).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId('catalog').textContent).toBe(
    JSON.stringify({ commands: [], skills: [], actions: [] }),
  );

  // Close and reopen: still only 1 call (catalog is cached).
  act(() => screen.getByText('toggle').click()); // close
  await act(async () => { screen.getByText('openAssistant').click(); }); // reopen
  expect(fetchAssistantCatalog).toHaveBeenCalledTimes(1);
});

it('addLocalExchange appends a user and a local message', async () => {
  let hookRef;
  const Grab = () => { hookRef = useAssistantDrawer(); return null; };
  render(<AssistantDrawerProvider><Probe /><Grab /></AssistantDrawerProvider>);

  // Capture initial messages count (should be empty).
  expect(hookRef.messages).toHaveLength(0);

  // Invoke addLocalExchange.
  act(() => { hookRef.addLocalExchange('/help', 'HELP TEXT'); });

  // Two messages appended: user turn then local response.
  expect(hookRef.messages).toHaveLength(2);
  expect(hookRef.messages[0]).toMatchObject({ role: 'user', text: '/help', atIndex: 0 });
  expect(hookRef.messages[1]).toMatchObject({ role: 'local', text: 'HELP TEXT', atIndex: 0 });
});

describe('closePanel', () => {
  it('closes only the named panel; the terminal stays open and becomes active', () => {
    render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
    act(() => screen.getByText('openAssistant').click());
    act(() => screen.getByText('openTerminal').click());
    act(() => screen.getByText('openAssistant').click()); // assistant active again
    expect(screen.getByTestId('panels').textContent).toBe('["assistant","terminal"]');
    expect(screen.getByTestId('active').textContent).toBe('assistant');
    act(() => screen.getByText('closeAssistantPanel').click());
    expect(screen.getByTestId('panels').textContent).toBe('["terminal"]');
    expect(screen.getByTestId('active').textContent).toBe('terminal');
    expect(screen.getByTestId('open').textContent).toBe('true'); // drawer stays open
  });

  it('closing a non-active panel does not steal the active tab', () => {
    render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
    act(() => screen.getByText('openAssistant').click());
    act(() => screen.getByText('openTerminal').click()); // terminal is active
    act(() => screen.getByText('closeAssistantPanel').click());
    expect(screen.getByTestId('panels').textContent).toBe('["terminal"]');
    expect(screen.getByTestId('active').textContent).toBe('terminal');
  });

  it('no-ops when the panel is not open', () => {
    render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
    act(() => screen.getByText('openTerminal').click());
    act(() => screen.getByText('closeAssistantPanel').click());
    expect(screen.getByTestId('panels').textContent).toBe('["terminal"]');
  });
});
