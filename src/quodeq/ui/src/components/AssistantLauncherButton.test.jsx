import { it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const drawerState = { isOpen: false, activeTab: 'assistant' };
const openTab = vi.fn();
vi.mock('../features/assistant/AssistantDrawerProvider.jsx', () => ({
  useAssistantDrawer: () => ({ isOpen: drawerState.isOpen, activeTab: drawerState.activeTab, openTab }),
}));
import { AssistantLauncherButton } from './AssistantLauncherButton.jsx';

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  drawerState.isOpen = false;
  drawerState.activeTab = 'assistant';
});
afterEach(() => localStorage.clear());

it('is hidden when the assistant is disabled (the default)', () => {
  const { container } = render(<AssistantLauncherButton />);
  expect(container).toBeEmptyDOMElement();
  expect(screen.queryByRole('button', { name: /assistant/i })).toBeNull();
});

it('is an icon-only labelled toggle when enabled', () => {
  localStorage.setItem('cc-assistant-enabled', 'true');
  render(<AssistantLauncherButton />);
  const btn = screen.getByRole('button', { name: /assistant/i });
  expect(btn).toHaveClass('topbar-btn', 'topbar-btn--icon');
  expect(btn).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(btn);
  expect(openTab).toHaveBeenCalledWith('assistant');
});

it('shows the active (highlighted) state when the drawer displays the assistant tab', () => {
  localStorage.setItem('cc-assistant-enabled', 'true');
  drawerState.isOpen = true;
  drawerState.activeTab = 'assistant';
  render(<AssistantLauncherButton />);
  const btn = screen.getByRole('button', { name: /assistant/i });
  expect(btn).toHaveClass('topbar-btn--assistant--open');
  expect(btn).toHaveAttribute('aria-pressed', 'true');
});

it('is NOT active when the drawer is open on the terminal tab', () => {
  localStorage.setItem('cc-assistant-enabled', 'true');
  drawerState.isOpen = true;
  drawerState.activeTab = 'terminal';
  render(<AssistantLauncherButton />);
  const btn = screen.getByRole('button', { name: /assistant/i });
  expect(btn).not.toHaveClass('topbar-btn--assistant--open');
  expect(btn).toHaveAttribute('aria-pressed', 'false');
});
