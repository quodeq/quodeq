import { describe, it, expect, vi } from 'vitest';
import { isActivationKey, activateOnKey, focusables, trapTab, restoreFocus } from './a11y.js';

describe('activation keys', () => {
  it('Enter and Space activate, other keys do not', () => {
    expect(isActivationKey({ key: 'Enter' })).toBe(true);
    expect(isActivationKey({ key: ' ' })).toBe(true);
    expect(isActivationKey({ key: 'a' })).toBe(false);
    expect(isActivationKey({ key: 'Escape' })).toBe(false);
  });

  it('activateOnKey prevents default and calls the handler once', () => {
    const handler = vi.fn();
    const preventDefault = vi.fn();
    activateOnKey(handler)({ key: ' ', preventDefault });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(preventDefault).toHaveBeenCalledTimes(1);
    activateOnKey(handler)({ key: 'Tab', preventDefault });
    expect(handler).toHaveBeenCalledTimes(1);
  });
});

describe('focus helpers', () => {
  function shell() {
    document.body.innerHTML =
      '<div id="root"><button id="a">a</button><a href="#">b</a><input id="c" disabled /><span tabindex="-1">d</span><button id="e">e</button></div>';
    return document.getElementById('root');
  }

  it('focusables skips disabled controls and tabindex -1', () => {
    const ids = focusables(shell()).map((el) => el.id || el.tagName);
    expect(ids).toEqual(['a', 'A', 'e']);
  });

  it('trapTab wraps from last to first and first to last', () => {
    const root = shell();
    const [first, , last] = focusables(root);
    last.focus();
    const forward = { key: 'Tab', shiftKey: false, preventDefault: vi.fn() };
    trapTab(root, forward);
    expect(document.activeElement).toBe(first);
    expect(forward.preventDefault).toHaveBeenCalled();
    const backward = { key: 'Tab', shiftKey: true, preventDefault: vi.fn() };
    trapTab(root, backward);
    expect(document.activeElement).toBe(last);
  });

  it('trapTab pulls focus inside root when it started outside', () => {
    const root = shell();
    const outside = document.createElement('button');
    document.body.appendChild(outside);
    outside.focus();
    const forward = { key: 'Tab', shiftKey: false, preventDefault: vi.fn() };
    trapTab(root, forward);
    expect(document.activeElement).toBe(focusables(root)[0]);
    expect(forward.preventDefault).toHaveBeenCalled();
    outside.focus();
    const backward = { key: 'Tab', shiftKey: true, preventDefault: vi.fn() };
    trapTab(root, backward);
    expect(document.activeElement).toBe(focusables(root)[2]);
  });

  it('trapTab ignores non-Tab keys', () => {
    const root = shell();
    const e = { key: 'Enter', preventDefault: vi.fn() };
    trapTab(root, e);
    expect(e.preventDefault).not.toHaveBeenCalled();
  });

  it('restoreFocus focuses a connected element and ignores a detached one', () => {
    const root = shell();
    const [first] = focusables(root);
    restoreFocus(first);
    expect(document.activeElement).toBe(first);
    const gone = document.createElement('button');
    expect(() => restoreFocus(gone)).not.toThrow();
    expect(() => restoreFocus(null)).not.toThrow();
  });
});
