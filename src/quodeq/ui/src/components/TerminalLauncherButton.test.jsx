import { it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawerState = { isOpen: false, activeTab: 'terminal' };
const openTab = vi.fn();
vi.mock('../features/assistant/AssistantDrawerProvider.jsx', () => ({
  useAssistantDrawer: () => ({ isOpen: drawerState.isOpen, activeTab: drawerState.activeTab, openTab }),
}));
import { TerminalLauncherButton } from './TerminalLauncherButton.jsx';

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  drawerState.isOpen = false;
  drawerState.activeTab = 'terminal';
});
afterEach(() => localStorage.clear());

it('is hidden when the terminal is disabled (the default)', () => {
  const { container } = render(<TerminalLauncherButton />);
  expect(container).toBeEmptyDOMElement();
  expect(screen.queryByRole('button', { name: /terminal/i })).toBeNull();
});

it('renders and opens the terminal tab when enabled', () => {
  localStorage.setItem('cc-terminal-enabled', 'true');
  render(<TerminalLauncherButton />);
  const btn = screen.getByRole('button', { name: /terminal/i });
  expect(btn).toHaveClass('topbar-btn', 'topbar-btn--icon');
  expect(btn).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(btn);
  expect(openTab).toHaveBeenCalledWith('terminal');
});

it('shows the active (highlighted) state when the drawer displays the terminal tab', () => {
  localStorage.setItem('cc-terminal-enabled', 'true');
  drawerState.isOpen = true;
  drawerState.activeTab = 'terminal';
  render(<TerminalLauncherButton />);
  const btn = screen.getByRole('button', { name: /terminal/i });
  expect(btn).toHaveClass('topbar-btn--terminal--open');
  expect(btn).toHaveAttribute('aria-pressed', 'true');
});
