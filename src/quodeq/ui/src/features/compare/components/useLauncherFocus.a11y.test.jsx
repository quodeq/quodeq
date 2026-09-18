import { describe, it, expect, vi } from 'vitest';
import { useRef } from 'react';
import { createPortal } from 'react-dom';
import { render, screen, fireEvent } from '@testing-library/react';
import { useLauncherFocus } from './useLauncherFocus.js';

const ITEMS = ['one', 'two', 'three'];

/* Mirrors both launcher triggers: a button in the tree plus a menu portaled
   to document.body, so the test exercises the real DOM-order problem the
   hook exists to solve. `open` is a prop so a rerender drives open/close;
   `extra` stands in for the duel menu's unpin button, a focusable inside the
   menu that is not one of the options. */
function Launcher({ open, close, items = ITEMS, extra = false }) {
  const btnRef = useRef(null);
  const menuRef = useRef(null);
  useLauncherFocus(open, btnRef, menuRef, close);
  return (
    <span>
      <button ref={btnRef} type="button">launch</button>
      {open && createPortal(
        <span className="menu" role="menu" ref={menuRef}>
          {extra && <button type="button">clear</button>}
          {items.map((label) => (
            <button key={label} type="button" role="menuitem">{label}</button>
          ))}
        </span>,
        document.body,
      )}
      <button type="button">after</button>
    </span>
  );
}

const item = (name) => screen.getByRole('menuitem', { name });
const trigger = () => screen.getByRole('button', { name: 'launch' });

function open(close = vi.fn(), props = {}) {
  const view = render(<Launcher open={false} close={close} {...props} />);
  trigger().focus();
  view.rerender(<Launcher open close={close} {...props} />);
  return view;
}

describe('useLauncherFocus', () => {
  it('moves focus to the first menu item when the menu opens', () => {
    open();
    expect(item('one')).toHaveFocus();
  });

  it('prefers the first option over any other focusable in the menu', () => {
    open(vi.fn(), { extra: true });
    expect(item('one')).toHaveFocus();
  });

  it('ArrowDown moves focus to the next item', () => {
    open();
    fireEvent.keyDown(item('one'), { key: 'ArrowDown' });
    expect(item('two')).toHaveFocus();
  });

  it('ArrowUp from the first item wraps to the last', () => {
    open();
    fireEvent.keyDown(item('one'), { key: 'ArrowUp' });
    expect(item('three')).toHaveFocus();
  });

  it('ArrowDown from the last item wraps to the first', () => {
    open();
    item('three').focus();
    fireEvent.keyDown(item('three'), { key: 'ArrowDown' });
    expect(item('one')).toHaveFocus();
  });

  it('walks onto a focusable that is not one of the options', () => {
    open(vi.fn(), { extra: true });
    fireEvent.keyDown(item('one'), { key: 'ArrowUp' });
    expect(screen.getByRole('button', { name: 'clear' })).toHaveFocus();
  });

  it('Tab closes the menu and returns focus to the trigger', () => {
    const close = vi.fn();
    open(close);
    fireEvent.keyDown(item('one'), { key: 'Tab' });
    expect(close).toHaveBeenCalled();
    expect(trigger()).toHaveFocus();
  });

  it('Shift+Tab closes the menu and returns focus to the trigger', () => {
    const close = vi.fn();
    open(close);
    fireEvent.keyDown(item('one'), { key: 'Tab', shiftKey: true });
    expect(close).toHaveBeenCalled();
    expect(trigger()).toHaveFocus();
  });

  it('returns focus to the trigger when the menu closes', () => {
    const close = vi.fn();
    const { rerender } = open(close);
    expect(item('one')).toHaveFocus();
    rerender(<Launcher open={false} close={close} />);
    expect(trigger()).toHaveFocus();
  });

  it('leaves focus alone when it moved outside the menu before closing', () => {
    const close = vi.fn();
    const { rerender } = open(close);
    const after = screen.getByRole('button', { name: 'after' });
    after.focus();
    rerender(<Launcher open={false} close={close} />);
    expect(after).toHaveFocus();
  });

  it('recovers focus when the open menu drops the focused option', () => {
    const close = vi.fn();
    const { rerender } = open(close);
    item('two').focus();
    rerender(<Launcher open close={close} items={['one', 'three']} />);
    expect(item('one')).toHaveFocus();
  });
});
