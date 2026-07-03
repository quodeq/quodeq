import { it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const toggle = vi.fn();
vi.mock('../features/assistant/AssistantDrawerProvider.jsx', () => ({
  useAssistantDrawer: () => ({ isOpen: false, toggle }),
}));
import { AssistantLauncherButton } from './AssistantLauncherButton.jsx';

beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });
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
  expect(toggle).toHaveBeenCalledTimes(1);
});
