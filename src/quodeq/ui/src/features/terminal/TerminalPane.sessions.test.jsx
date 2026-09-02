import { it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Split from TerminalPane.test.jsx: multi-session tabs, creation/close,
// visibility, tab-selection persistence, copy, and OSC 8 hyperlinks. The
// full mock header is duplicated here (rather than shared) because
// vi.mock hoisting and the mutable closures it captures are file-scoped.

const fakeTerm = { open: vi.fn(), write: vi.fn(), dispose: vi.fn(), loadAddon: vi.fn(),
  onData: vi.fn(), onResize: vi.fn(), focus: vi.fn(), attachCustomKeyEventHandler: vi.fn(),
  reset: vi.fn(), getSelection: vi.fn(() => ''),
  registerLinkProvider: vi.fn(() => ({ dispose: vi.fn() })),
  buffer: { active: { getLine: () => ({ translateToString: () => '' }), viewportY: 0 } },
  cols: 80, rows: 24, options: {} };
// Use `function` (not arrow) implementations so vi.fn() produces a constructible
// mock: xterm's Terminal/FitAddon are always invoked with `new` in the views.
vi.mock('@xterm/xterm', () => ({ Terminal: vi.fn(function Terminal() { return fakeTerm; }) }));
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: vi.fn(function FitAddon() { return { fit: vi.fn(), proposeDimensions: () => ({ cols: 80, rows: 24 }) }; }),
}));

// Server-side session registry stub the pane reconciles against.
let fakeSessions = [];
let nextSession = 2;
const listTerminalSessions = vi.fn(async () => ({ sessions: fakeSessions, max: 6 }));
const createTerminalSession = vi.fn(async () => {
  const s = { id: `s${nextSession}`, name: `zsh · ${nextSession}`, alive: true, cwd: '~/proj' };
  nextSession += 1;
  fakeSessions = fakeSessions.concat([s]);
  return { id: s.id, name: s.name };
});
const killTerminalSession = vi.fn(async (id) => { fakeSessions = fakeSessions.filter((s) => s.id !== id); return { ok: true }; });

vi.mock('../../api/terminal.js', () => ({
  terminalStatus: vi.fn(async () => ({ enabled: true, running: false, reason: null, shell: 'zsh' })),
  killTerminal: vi.fn(async () => ({ ok: true })),
  terminalSocketUrl: () => 'ws://localhost/api/terminal/ws',
  listTerminalSessions: (...a) => listTerminalSessions(...a),
  createTerminalSession: (...a) => createTerminalSession(...a),
  killTerminalSession: (...a) => killTerminalSession(...a),
  resolveTerminalPaths: vi.fn(async () => []),
  openInEditor: vi.fn(async () => ({ opened: true, editor: 'code' })),
}));
// Mock the socket hook: jsdom has no real terminal WS to reach.
const socketState = { status: 'open', send: vi.fn(), resize: vi.fn(), reconnectNow: vi.fn() };
vi.mock('./useTerminalSocket.js', () => ({
  useTerminalSocket: vi.fn((opts) => { return socketState; }),
}));
// The header/panel switcher read the drawer context; the pane is rendered
// bare here, so stub the hook.
const drawerCtx = {
  openPanels: ['terminal'], activeTab: 'terminal', selectTab: vi.fn(),
  maximized: false, toggleMaximized: vi.fn(), closeActiveTab: vi.fn(),
};
vi.mock('../assistant/AssistantDrawerProvider.jsx', () => ({
  useAssistantDrawer: () => drawerCtx,
}));
import TerminalPane from './TerminalPane.jsx';

beforeEach(() => {
  window.localStorage.clear();
  fakeSessions = [{ id: 's1', name: 'zsh · 1', alive: true, cwd: '~/proj' }];
  nextSession = 2;
  listTerminalSessions.mockClear();
  createTerminalSession.mockClear();
  killTerminalSession.mockClear();
  socketState.status = 'open';
});

it('renders one tab per server session and passes each id to its own socket', async () => {
  fakeSessions = [
    { id: 's1', name: 'zsh · 1', alive: true, cwd: '~/proj' },
    { id: 's9', name: 'zsh · 9', alive: true, cwd: '~/other' },
  ];
  render(<TerminalPane active />);
  await screen.findByRole('tab', { name: /zsh · 1/ });
  expect(screen.getByRole('tab', { name: /zsh · 9/ })).toBeInTheDocument();
  expect(screen.getAllByTestId('tty-root')).toHaveLength(2);
  // Every view opened a socket for ITS session (the mock captures the last).
  const { useTerminalSocket } = await import('./useTerminalSocket.js');
  const ids = useTerminalSocket.mock.calls.map(([opts]) => opts.sessionId);
  expect(ids).toContain('s1');
  expect(ids).toContain('s9');
});

it('creates a session on the header "+" and reveals the tab strip with the new one active', async () => {
  const { userEvent } = await import('@testing-library/user-event').then((m) => ({ userEvent: m.default }));
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  await userEvent.click(screen.getByRole('button', { name: 'New session' }));
  expect(createTerminalSession).toHaveBeenCalled();
  const newTab = await screen.findByRole('tab', { name: /zsh · 2/ });
  expect(newTab).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('tab', { name: /zsh · 1/ })).toBeInTheDocument();
});

it('creates one session automatically when the server has none (never zero sessions)', async () => {
  fakeSessions = [];
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');   // the auto-created session's view
  expect(createTerminalSession).toHaveBeenCalled();
});

it('hides the tab strip with a single session and shows the "+" in the header instead', async () => {
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  expect(screen.queryByRole('tablist', { name: 'Terminal sessions' })).toBeNull();
  const add = screen.getByRole('button', { name: 'New session' });
  expect(add.closest('.tty-panel-header')).not.toBeNull();
});

it('closing a tab kills that session server-side and keeps the neighbor', async () => {
  const { userEvent } = await import('@testing-library/user-event').then((m) => ({ userEvent: m.default }));
  fakeSessions = [
    { id: 's1', name: 'zsh · 1', alive: true, cwd: '~/proj' },
    { id: 's9', name: 'zsh · 9', alive: true, cwd: '~/other' },
  ];
  render(<TerminalPane active />);
  await screen.findByRole('tab', { name: /zsh · 9/ });
  await userEvent.click(screen.getByRole('button', { name: 'Close zsh · 9' }));
  expect(killTerminalSession).toHaveBeenCalledWith('s9');
  await waitFor(() => expect(screen.queryByRole('tab', { name: /zsh · 9/ })).toBeNull());
  // Down to one session the strip collapses; the survivor's view remains.
  expect(screen.getAllByTestId('tty-root')).toHaveLength(1);
  expect(screen.getByText('1 session')).toBeInTheDocument();
});

it('a lone session exposes no close button (the panel never shows zero sessions)', async () => {
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  expect(screen.queryByRole('button', { name: /Close zsh/ })).toBeNull();
});

it('only the active session view is visible; the other stays mounted but hidden', async () => {
  const { userEvent } = await import('@testing-library/user-event').then((m) => ({ userEvent: m.default }));
  fakeSessions = [
    { id: 's1', name: 'zsh · 1', alive: true, cwd: '~/proj' },
    { id: 's9', name: 'zsh · 9', alive: true, cwd: '~/other' },
  ];
  render(<TerminalPane active />);
  await screen.findByRole('tab', { name: /zsh · 9/ });
  await userEvent.click(screen.getByRole('tab', { name: /zsh · 9/ }));
  const wraps = screen.getAllByTestId('tty-root').map((el) => el.parentElement);
  const hidden = wraps.filter((w) => w.style.display === 'none');
  expect(wraps).toHaveLength(2);   // both mounted (PTYs survive the switch)
  expect(hidden).toHaveLength(1);  // exactly one hidden
});

it('restores the previously selected tab when the pane remounts (drawer closed and reopened)', async () => {
  const { userEvent } = await import('@testing-library/user-event').then((m) => ({ userEvent: m.default }));
  fakeSessions = [
    { id: 's1', name: 'zsh · 1', alive: true, cwd: '~/proj' },
    { id: 's5', name: 'zsh · 5', alive: true, cwd: '~/mid' },
    { id: 's9', name: 'zsh · 9', alive: true, cwd: '~/other' },
  ];
  const first = render(<TerminalPane active />);
  await screen.findByRole('tab', { name: /zsh · 5/ });
  await userEvent.click(screen.getByRole('tab', { name: /zsh · 5/ }));
  expect(screen.getByRole('tab', { name: /zsh · 5/ })).toHaveAttribute('aria-selected', 'true');
  // Closing the drawer unmounts the whole pane; reopening mounts it fresh.
  first.unmount();
  render(<TerminalPane active />);
  const tab = await screen.findByRole('tab', { name: /zsh · 5/ });
  await waitFor(() => expect(tab).toHaveAttribute('aria-selected', 'true'));
});

it('falls back to the newest session when the stored selection no longer exists', async () => {
  window.localStorage.setItem('quodeq.terminal.activeSession', 'dead-id');
  fakeSessions = [
    { id: 's1', name: 'zsh · 1', alive: true, cwd: '~/proj' },
    { id: 's9', name: 'zsh · 9', alive: true, cwd: '~/other' },
  ];
  render(<TerminalPane active />);
  const tab = await screen.findByRole('tab', { name: /zsh · 9/ });
  await waitFor(() => expect(tab).toHaveAttribute('aria-selected', 'true'));
});

it('copy button copies the active session selection to the clipboard', async () => {
  const { userEvent } = await import('@testing-library/user-event').then((m) => ({ userEvent: m.default }));
  const writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  fakeTerm.getSelection.mockReturnValue('picked text');
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  await userEvent.click(screen.getByRole('button', { name: 'Copy terminal output' }));
  expect(writeText).toHaveBeenCalledWith('picked text');
});

// OSC 8 hyperlinks are activated by xterm itself. Without an explicit
// linkHandler xterm uses its built-in one, which confirms and then calls
// window.open() with no URL — null inside pywebview's WKWebView, so clicking OK
// did nothing. The handler must reach the pywebview bridge instead.
it('routes OSC 8 hyperlink clicks through the pywebview bridge, not window.open', async () => {
  const { Terminal } = await import('@xterm/xterm');
  Terminal.mockClear();
  const open_browser = vi.fn();
  window.pywebview = { api: { open_browser } };
  const windowOpen = vi.spyOn(window, 'open').mockReturnValue(null);
  try {
    render(<TerminalPane active />);
    await screen.findByTestId('tty-root');
    await waitFor(() => expect(Terminal).toHaveBeenCalled());

    const { linkHandler } = Terminal.mock.calls[0][0];
    expect(linkHandler).toBeTruthy();
    linkHandler.activate({}, 'https://example.com/release');

    expect(open_browser).toHaveBeenCalledWith('https://example.com/release');
    expect(windowOpen).not.toHaveBeenCalled();
  } finally {
    windowOpen.mockRestore();
    delete window.pywebview;
  }
});

it('shows shell, session count, sandbox note and active cwd in the status bar', async () => {
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  expect(screen.getByText('zsh')).toBeInTheDocument();
  expect(screen.getByText('1 session')).toBeInTheDocument();
  expect(screen.getByText('localhost only')).toBeInTheDocument();
  expect(screen.getByText('~/proj')).toBeInTheDocument();
});
