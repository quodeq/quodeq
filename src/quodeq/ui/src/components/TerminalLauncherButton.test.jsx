import { it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawerState = { openPanels: [] };
const toggleTopbar = vi.fn();
vi.mock('../features/assistant/AssistantDrawerProvider.jsx', () => ({
  useAssistantDrawer: () => ({ openPanels: drawerState.openPanels, toggleTopbar }),
}));
import { TerminalLauncherButton } from './TerminalLauncherButton.jsx';

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  drawerState.openPanels = [];
});
afterEach(() => localStorage.clear());

it('is hidden when the terminal is disabled (the default)', () => {
  const { container } = render(<TerminalLauncherButton />);
  expect(container).toBeEmptyDOMElement();
  expect(screen.queryByRole('button', { name: /terminal/i })).toBeNull();
});

it('renders and toggles the terminal panel when enabled', () => {
  localStorage.setItem('cc-terminal-enabled', 'true');
  render(<TerminalLauncherButton />);
  const btn = screen.getByRole('button', { name: /terminal/i });
  expect(btn).toHaveClass('topbar-btn', 'topbar-btn--icon');
  expect(btn).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(btn);
  expect(toggleTopbar).toHaveBeenCalledWith('terminal');
});

it('is highlighted (active) when the terminal panel is open', () => {
  localStorage.setItem('cc-terminal-enabled', 'true');
  drawerState.openPanels = ['terminal'];
  render(<TerminalLauncherButton />);
  const btn = screen.getByRole('button', { name: /terminal/i });
  expect(btn).toHaveClass('topbar-btn--terminal--open');
  expect(btn).toHaveAttribute('aria-pressed', 'true');
});

it('stays highlighted when BOTH panels are open', () => {
  localStorage.setItem('cc-terminal-enabled', 'true');
  drawerState.openPanels = ['assistant', 'terminal'];
  render(<TerminalLauncherButton />);
  expect(screen.getByRole('button', { name: /terminal/i })).toHaveClass('topbar-btn--terminal--open');
});
