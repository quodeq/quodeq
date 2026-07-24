import { it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const fakeTerm = { open: vi.fn(), write: vi.fn(), dispose: vi.fn(), loadAddon: vi.fn(),
  onData: vi.fn(), onResize: vi.fn(), focus: vi.fn(), attachCustomKeyEventHandler: vi.fn(),
  reset: vi.fn(),
  cols: 80, rows: 24, options: {} };
// Use `function` (not arrow) implementations so vi.fn() produces a constructible
// mock: xterm's Terminal/FitAddon are always invoked with `new` in TerminalPane.
vi.mock('@xterm/xterm', () => ({ Terminal: vi.fn(function Terminal() { return fakeTerm; }) }));
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: vi.fn(function FitAddon() { return { fit: vi.fn(), proposeDimensions: () => ({ cols: 80, rows: 24 }) }; }),
}));
vi.mock('../../api/terminal.js', () => ({
  terminalStatus: vi.fn(async () => ({ enabled: true, running: false, reason: null })),
  killTerminal: vi.fn(async () => ({ ok: true })),
  terminalSocketUrl: () => 'ws://localhost/api/terminal/ws',
}));
// Mock the socket hook: jsdom has no real terminal WS to reach, and the
// overlay tests need to drive each connection status directly. lastSocketOpts
// captures the options so a test can invoke the pane's onOpen callback.
const socketState = { status: 'open', send: vi.fn(), resize: vi.fn(), reconnectNow: vi.fn() };
let lastSocketOpts = null;
vi.mock('./useTerminalSocket.js', () => ({
  useTerminalSocket: vi.fn((opts) => { lastSocketOpts = opts; return socketState; }),
}));
import TerminalPane from './TerminalPane.jsx';

it('mounts an xterm terminal when active', async () => {
  const { Terminal } = await import('@xterm/xterm');
  render(<TerminalPane active />);
  // allow the status effect to resolve
  await screen.findByTestId('tty-root');
  expect(Terminal).toHaveBeenCalled();
  expect(fakeTerm.open).toHaveBeenCalled();
});

it('focuses xterm when it is the active tab so the user can type without clicking in', async () => {
  socketState.status = 'open';
  fakeTerm.focus.mockClear();
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  expect(fakeTerm.focus).toHaveBeenCalled();
});

it('does not focus xterm while backgrounded (active=false)', async () => {
  socketState.status = 'open';
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
  expect(Terminal).toHaveBeenCalled();
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
  socketState.status = 'open';
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
  const { vi: _vi } = await import('vitest');
  socketState.status = 'open';
  fakeTerm.reset.mockClear();
  fakeTerm.options = {};
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  // Simulate the socket (re)opening: the pane's onOpen must reset the screen
  // BEFORE the server's scrollback replay lands, and re-enable input.
  expect(typeof lastSocketOpts.onOpen).toBe('function');
  lastSocketOpts.onOpen();
  expect(fakeTerm.reset).toHaveBeenCalled();
  expect(fakeTerm.options.disableStdin).toBe(false);
});

it('disables stdin while disconnected so keystrokes are not silently swallowed', async () => {
  socketState.status = 'reconnecting';
  fakeTerm.options = {};
  render(<TerminalPane active />);
  await screen.findByTestId('tty-root');
  expect(fakeTerm.options.disableStdin).toBe(true);
});
