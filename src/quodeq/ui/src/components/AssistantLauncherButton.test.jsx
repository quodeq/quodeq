import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const toggle = vi.fn();
vi.mock('../features/assistant/AssistantDrawerProvider.jsx', () => ({
  useAssistantDrawer: () => ({ isOpen: false, toggle }),
}));
import { AssistantLauncherButton } from './AssistantLauncherButton.jsx';

it('is an icon-only labelled toggle', () => {
  render(<AssistantLauncherButton />);
  const btn = screen.getByRole('button', { name: /assistant/i });
  expect(btn).toHaveClass('topbar-btn', 'topbar-btn--icon');
  expect(btn).toHaveAttribute('aria-pressed', 'false');
  fireEvent.click(btn);
  expect(toggle).toHaveBeenCalledTimes(1);
});
