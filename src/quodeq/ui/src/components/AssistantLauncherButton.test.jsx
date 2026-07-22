import { it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawerState = { openPanels: [] };
const toggleTopbar = vi.fn();
vi.mock('../features/assistant/AssistantDrawerProvider.jsx', () => ({
  useAssistantDrawer: () => ({ openPanels: drawerState.openPanels, toggleTopbar }),
}));
import { AssistantLauncherButton } from './AssistantLauncherButton.jsx';

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  drawerState.openPanels = [];
});
afterEach(() => localStorage.clear());

it('is hidden when the assistant is explicitly disabled in Settings', () => {
  localStorage.setItem('cc-assistant-enabled', 'false');
  const { container } = render(<AssistantLauncherButton />);
  expect(container).toBeEmptyDOMElement();
  expect(screen.queryByRole('button', { name: /assistant/i })).toBeNull();
});

it('is an icon-only labelled toggle by default (enabled); click toggles the panel', () => {
  render(<AssistantLauncherButton />);
  const btn = screen.getByRole('button', { name: /assistant/i });
  expect(btn).toHaveClass('topbar-btn', 'topbar-btn--icon');
  expect(btn).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(btn);
  expect(toggleTopbar).toHaveBeenCalledWith('assistant');
});

it('is highlighted (active) when the assistant panel is open', () => {
  localStorage.setItem('cc-assistant-enabled', 'true');
  drawerState.openPanels = ['assistant'];
  render(<AssistantLauncherButton />);
  const btn = screen.getByRole('button', { name: /assistant/i });
  expect(btn).toHaveClass('topbar-btn--assistant--open');
  expect(btn).toHaveAttribute('aria-pressed', 'true');
});

it('stays highlighted when BOTH panels are open (both launchers selected)', () => {
  localStorage.setItem('cc-assistant-enabled', 'true');
  drawerState.openPanels = ['terminal', 'assistant'];
  render(<AssistantLauncherButton />);
  expect(screen.getByRole('button', { name: /assistant/i })).toHaveClass('topbar-btn--assistant--open');
});

it('is NOT highlighted when only the terminal panel is open', () => {
  localStorage.setItem('cc-assistant-enabled', 'true');
  drawerState.openPanels = ['terminal'];
  render(<AssistantLauncherButton />);
  const btn = screen.getByRole('button', { name: /assistant/i });
  expect(btn).not.toHaveClass('topbar-btn--assistant--open');
  expect(btn).toHaveAttribute('aria-pressed', 'false');
});

it('on a remote project: visible but disabled, tooltip explains why, click is a no-op', () => {
  render(<AssistantLauncherButton sharedSource />);
  const btn = screen.getByRole('button', { name: /assistant is unavailable on remote projects/i });
  expect(btn).toHaveAttribute('aria-disabled', 'true');
  expect(btn).toHaveAttribute('title', 'Assistant is unavailable on remote projects (read-only)');
  fireEvent.click(btn);
  expect(toggleTopbar).not.toHaveBeenCalled();
});

it('sharedSource does not override the Settings kill switch', () => {
  localStorage.setItem('cc-assistant-enabled', 'false');
  const { container } = render(<AssistantLauncherButton sharedSource />);
  expect(container).toBeEmptyDOMElement();
});
