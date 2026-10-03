import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { APP_VISIBILITY_EVENT } from '../constants.js';
import { isHidden, subscribeVisibility, resetAppVisibilityForTest } from './appVisibility.js';

function shellVisibility(hidden) {
  window.dispatchEvent(new CustomEvent(APP_VISIBILITY_EVENT, { detail: { hidden } }));
}

describe('appVisibility', () => {
  beforeEach(() => { resetAppVisibilityForTest(); });
  afterEach(() => {
    resetAppVisibilityForTest();
    vi.restoreAllMocks();
  });

  it('reports visible until the shell says otherwise', () => {
    expect(isHidden()).toBe(false);
    shellVisibility(true);
    expect(isHidden()).toBe(true);
    shellVisibility(false);
    expect(isHidden()).toBe(false);
  });

  // The desktop window never changes visibilityState, so the browser signal
  // has to stand on its own for tabs.
  it('reports hidden from the document alone', () => {
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    expect(isHidden()).toBe(true);
  });

  it('notifies subscribers on a shell change and stops after unsubscribe', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeVisibility(listener);

    shellVisibility(true);
    expect(listener).toHaveBeenCalledTimes(1);

    // Same state twice is not a change.
    shellVisibility(true);
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    shellVisibility(false);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('keeps notifying the other subscribers when one throws', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const good = vi.fn();
    subscribeVisibility(() => { throw new Error('bad listener'); });
    subscribeVisibility(good);

    shellVisibility(true);
    expect(good).toHaveBeenCalledTimes(1);
  });
});
