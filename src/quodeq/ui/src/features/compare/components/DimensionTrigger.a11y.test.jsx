import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DimensionTrigger from './DimensionTrigger.jsx';

const board = [
  { key: 'security', label: 'Security', avg: 7.2 },
  { key: 'usability', label: 'Usability', avg: 6.1 },
];

const launcher = () => screen.getByRole('button', { name: /Open a dimension/i });

async function openWithEnter(onOpen = vi.fn()) {
  const user = userEvent.setup();
  render(<DimensionTrigger board={board} onOpen={onOpen} />);
  launcher().focus();
  await user.keyboard('{Enter}');
  return user;
}

describe('DimensionTrigger accessibility (#6592)', () => {
  it('moves focus into the portaled menu when it opens from the keyboard', async () => {
    await openWithEnter();
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
  });

  it('walks the options with the arrow keys', async () => {
    const user = await openWithEnter();
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[1]).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
  });

  it('Tab closes the menu and returns focus to the trigger', async () => {
    const user = await openWithEnter();
    await user.keyboard('{Tab}');
    expect(screen.queryByRole('menu')).toBeNull();
    expect(launcher()).toHaveFocus();
    expect(launcher()).toHaveAttribute('aria-expanded', 'false');
  });

  it('picking an option still opens that dimension', async () => {
    const onOpen = vi.fn();
    const user = await openWithEnter(onOpen);
    await user.keyboard('{Enter}');
    expect(onOpen).toHaveBeenCalledWith('security');
  });
});
