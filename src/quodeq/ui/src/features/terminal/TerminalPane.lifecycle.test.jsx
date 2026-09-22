import { it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Split from TerminalPane.test.jsx: mount/focus lifecycle, the disabled
// gate, and the connection-status overlay. The full mock header is
// duplicated here (rather than shared) because vi.mock hoisting and the
// mutable closures it captures are file-scoped.

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
// Mock the socket hook: jsdom has no real terminal WS to reach, and the
// overlay tests need to drive each connection status directly. lastSocketOpts
// captures the options so a test can invoke a view's onOpen callback.
const socketState = { status: 'open', send: vi.fn(), resize: vi.fn(), reconnectNow: vi.fn() };
let lastSocketOpts = null;
vi.mock('./useTerminalSocket.js', () => ({
  useTerminalSocket: vi.fn((opts) => { lastSocketOpts = opts; return socketState; }),
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

it('mounts an xterm terminal when active', async () => {
  const { Terminal } = await import('@xterm/xterm');
  Terminal.mockClear();
  render(<TerminalPane active />);
  // allow the status + session-list effects to resolve
  await screen.findByTestId('tty-root');
  // waitFor, not a plain assert: tty-root appears on render commit but the
  // Terminal constructor runs in the view's mount EFFECT, which can land a
  // beat later under CI load (flaked once on a sync PR).
  await waitFor(() => expect(Terminal).toHaveBeenCalled());
  expect(fakeTerm.open).toHaveBeenCalled();
});

it('focuses xterm when it is the active tab so the user can type without clicking in', async () => {
  fakeTerm.focus.mockClear();
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  // waitFor, not a plain assert: focus() runs in a post-commit effect, so it
  // can land a beat after tty-root appears under CI load (flaked on develop,
  // same race the mount test above was hardened against).
  await waitFor(() => expect(fakeTerm.focus).toHaveBeenCalled());
});

it('does not focus xterm while backgrounded (active=false)', async () => {
  fakeTerm.focus.mockClear();
  render(<TerminalPane active={false} />);
  await screen.findByTestId('tty-root');
  expect(fakeTerm.focus).not.toHaveBeenCalled();
});

it('mounts xterm even when backgrounded (active=false) so the PTY survives a tab switch', async () => {
  const { Terminal } = await import('@xterm/xterm');
  Terminal.mockClear();
  // active=false means "not the frontmost tab" — the panel is still open, so
  // the terminal must still mount (lifecycle follows panel-open, not active).
  render(<TerminalPane active={false} />);
  await screen.findByTestId('tty-root');
  await waitFor(() => expect(Terminal).toHaveBeenCalled());
  expect(fakeTerm.open).toHaveBeenCalled();
});

it('shows the gate reason and does not mount xterm when disabled', async () => {
  const terminalApi = await import('../../api/terminal.js');
  terminalApi.terminalStatus.mockResolvedValueOnce({ enabled: false, running: false, reason: 'localhost only' });
  const { Terminal } = await import('@xterm/xterm');
  Terminal.mockClear(); // clear calls from any prior test in this file
  render(<TerminalPane active />);
  const disabled = await screen.findByTestId('tty-disabled');
  expect(disabled).toHaveTextContent('localhost only');
  expect(screen.queryByTestId('tty-root')).toBeNull();
  expect(Terminal).not.toHaveBeenCalled();
});

it('shows no overlay while the socket is open or on the initial connect', async () => {
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  expect(screen.queryByTestId('tty-overlay')).toBeNull();
  socketState.status = 'connecting';
  render(<TerminalPane active />);
  expect(screen.queryByTestId('tty-overlay')).toBeNull();
});

it('shows a reconnecting banner when the socket drops, and Retry calls reconnectNow', async () => {
  const { userEvent } = await import('@testing-library/user-event').then((m) => ({ userEvent: m.default }));
  socketState.status = 'reconnecting';
  socketState.reconnectNow = vi.fn();
  render(<TerminalPane active />);
  const overlay = await screen.findByTestId('tty-overlay');
  expect(overlay).toHaveTextContent('Terminal disconnected. Reconnecting');
  await userEvent.click(screen.getByRole('button', { name: 'Retry now' }));
  expect(socketState.reconnectNow).toHaveBeenCalled();
});

it('shows a busy banner and an honest Retry (not a fake takeover) when another window owns the terminal', async () => {
  socketState.status = 'busy';
  render(<TerminalPane active />);
  const overlay = await screen.findByTestId('tty-overlay');
  expect(overlay).toHaveTextContent('open in another window');
  // The old "Use it here" button promised a takeover that never happened
  // (no lock eviction). The button must not claim to take over.
  expect(screen.queryByRole('button', { name: 'Use it here' })).toBeNull();
});

it('resets xterm on every socket (re)open so a live-backend reconnect does not duplicate scrollback', async () => {
  fakeTerm.reset.mockClear();
  fakeTerm.open.mockClear();
  fakeTerm.options = {};
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  // waitFor, not a plain assert: tty-root appears on the render commit, but
  // the xterm instance is constructed in the view's mount EFFECT, which is
  // what populates termRef. onOpen bails out silently on `if (!term) return`
  // until that effect has run, so driving it straight after findByTestId
  // races under CI load and reset() is never called. Third instance of the
  // post-commit-effect flake the mount and focus tests above already carry.
  await waitFor(() => expect(fakeTerm.open).toHaveBeenCalled());
  // Simulate the socket (re)opening: the view's onOpen must reset the screen
  // BEFORE the server's scrollback replay lands, and re-enable input.
  expect(typeof lastSocketOpts.onOpen).toBe('function');
  lastSocketOpts.onOpen();
  expect(fakeTerm.reset).toHaveBeenCalled();
  // Top breathing room: one blank buffer row ahead of the replayed content
  // (scrolls away with the scrollback, unlike a fixed CSS inset).
  expect(fakeTerm.write).toHaveBeenCalledWith('\r\n');
  expect(fakeTerm.options.disableStdin).toBe(false);
});

it('disables stdin while disconnected so keystrokes are not silently swallowed', async () => {
  socketState.status = 'reconnecting';
  fakeTerm.options = {};
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  // waitFor, not a plain assert: disableStdin is written by an effect in
  // TerminalSessionView that bails on `if (!term) return` until the mount
  // effect has constructed the xterm instance and populated termRef. tty-root
  // lands on the render commit, so asserting straight after findByTestId reads
  // fakeTerm.options before either effect has run and sees undefined, not
  // false. Fourth instance of the post-commit-effect flake the tests above
  // already carry; it took down an unrelated PR's ui job.
  await waitFor(() => expect(fakeTerm.options.disableStdin).toBe(true));
});
