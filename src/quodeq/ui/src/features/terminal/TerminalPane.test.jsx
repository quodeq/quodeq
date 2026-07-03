import { it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const fakeTerm = { open: vi.fn(), write: vi.fn(), dispose: vi.fn(), loadAddon: vi.fn(),
  onData: vi.fn(), onResize: vi.fn(), focus: vi.fn(), attachCustomKeyEventHandler: vi.fn(),
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
import TerminalPane from './TerminalPane.jsx';

it('mounts an xterm terminal when active', async () => {
  const { Terminal } = await import('@xterm/xterm');
  render(<TerminalPane active />);
  // allow the status effect to resolve
  await screen.findByTestId('tty-root');
  expect(Terminal).toHaveBeenCalled();
  expect(fakeTerm.open).toHaveBeenCalled();
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
