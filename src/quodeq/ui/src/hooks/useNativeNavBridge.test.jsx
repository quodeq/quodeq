import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useNativeNavBridge } from './useNativeNavBridge.js';

// The native (pywebview) shell dispatches quodeq:navigate CustomEvents via
// evaluate_js; the hook routes valid tab ids to navTab and drops the rest.

function fire(detail) {
  window.dispatchEvent(new CustomEvent('quodeq:navigate', { detail }));
}

describe('useNativeNavBridge', () => {
  it('routes known tabs to navTab', () => {
    const navTab = vi.fn();
    renderHook(() => useNativeNavBridge(navTab));
    fire('help');
    expect(navTab).toHaveBeenCalledTimes(1);
    expect(navTab).toHaveBeenCalledWith('help');
  });

  it('ignores details that are not known tabs', () => {
    const navTab = vi.fn();
    renderHook(() => useNativeNavBridge(navTab));
    fire('not-a-tab');
    fire(undefined);
    fire({ page: 'help' });
    expect(navTab).not.toHaveBeenCalled();
  });

  it('stops listening after unmount', () => {
    const navTab = vi.fn();
    const { unmount } = renderHook(() => useNativeNavBridge(navTab));
    unmount();
    fire('help');
    expect(navTab).not.toHaveBeenCalled();
  });
});
