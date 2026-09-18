import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DuelTrigger from './DuelTrigger.jsx';

const targets = [
  { id: 'alpha', name: 'Alpha', score: 7.2 },
  { id: 'beta', name: 'Beta', score: 6.1 },
  { id: 'gamma', name: 'Gamma', score: 5 },
];

const launcher = () => screen.getByRole('button', { name: /Start a duel/i });

async function openWithEnter(onStart = vi.fn()) {
  const user = userEvent.setup();
  render(<DuelTrigger targets={targets} onStart={onStart} />);
  launcher().focus();
  await user.keyboard('{Enter}');
  return user;
}

describe('DuelTrigger accessibility (#6593)', () => {
  it('moves focus into the portaled menu when it opens from the keyboard', async () => {
    await openWithEnter();
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
  });

  it('walks the candidates with the arrow keys, wrapping at the end', async () => {
    const user = await openWithEnter();
    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('menuitem')[targets.length - 1]).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('menuitem')[0]).toHaveFocus();
  });

  it('Tab closes the menu and returns focus to the trigger', async () => {
    const user = await openWithEnter();
    await user.keyboard('{Tab}');
    expect(screen.queryByRole('menu')).toBeNull();
    expect(launcher()).toHaveFocus();
    expect(launcher()).toHaveAttribute('aria-expanded', 'false');
  });

  it('keeps the two-pick flow reachable from the keyboard', async () => {
    const onStart = vi.fn();
    const user = await openWithEnter(onStart);
    // First pick pins side A; the list re-renders without it.
    await user.keyboard('{Enter}');
    expect(screen.getByRole('button', { name: /Clear the first pick/i })).toBeInTheDocument();
    await user.keyboard('{Enter}');
    expect(onStart).toHaveBeenCalledWith('alpha', 'beta');
  });
});
