/**
 * Finding #363: history.pushState inside setNavStack updater is a side effect
 * that React may double-invoke in Strict Mode. The updater must be pure.
 *
 * Fix: compute next from the ref, call setNavStack(next) + history.pushState
 * as two sequential statements outside the updater.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useNavStack } from './useNavStack.js';

/**
 * React Strict Mode double-invokes state updaters to catch side effects.
 * Wrap the hook in StrictMode to reproduce the double-invocation.
 */
function strictWrapper({ children }) {
  return <React.StrictMode>{children}</React.StrictMode>;
}


// Split from useNavStack.test.jsx: navTab params folding, navReplace
// (in-place tab flips), navSwapAt (breadcrumb sibling swaps), and the
// navPending transition flag.

describe('useNavStack navTab params', () => {
  let historyAdapter;

  beforeEach(() => {
    historyAdapter = {
      pushState: vi.fn(),
      replaceState: vi.fn(),
      back: vi.fn(),
      go: vi.fn(),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('folds extra params into the single reset entry', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navTab('evaluate', { preselectDims: ['security'] }); });

    expect(result.current.navStack).toHaveLength(1);
    expect(result.current.navStack[0].page).toBe('evaluate');
    expect(result.current.navStack[0].preselectDims).toEqual(['security']);
  });

  it('still works with no params (backward compatible)', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navTab('projects'); });

    expect(result.current.navStack).toHaveLength(1);
    expect(result.current.navStack[0].page).toBe('projects');
    expect(result.current.navStack[0].preselectDims).toBeUndefined();
  });
});

describe('useNavStack navReplace (repositories tab flips must not grow history)', () => {
  let historyAdapter;

  beforeEach(() => {
    historyAdapter = {
      pushState: vi.fn(),
      replaceState: vi.fn(),
      back: vi.fn(),
      go: vi.fn(),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('replaces the top entry without growing the stack', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navPush({ page: 'projects', sourceTab: 'local' }); });
    const lengthBefore = result.current.navStack.length;

    act(() => { result.current.navReplace({ page: 'projects', sourceTab: 'shared' }); });
    act(() => { result.current.navReplace({ page: 'projects', sourceTab: 'local' }); });
    act(() => { result.current.navReplace({ page: 'projects', sourceTab: 'shared' }); });

    expect(result.current.navStack).toHaveLength(lengthBefore);
    expect(result.current.navStack.at(-1).sourceTab).toBe('shared');
  });

  it('uses history.replaceState (never pushState) with the current navIndex', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navPush({ page: 'projects', sourceTab: 'local' }); });
    historyAdapter.pushState.mockClear();
    historyAdapter.replaceState.mockClear();

    act(() => { result.current.navReplace({ page: 'projects', sourceTab: 'shared' }); });

    expect(historyAdapter.pushState).not.toHaveBeenCalled();
    // Exactly once even under StrictMode double-invoke (same purity rule as navPush, #363).
    expect(historyAdapter.replaceState).toHaveBeenCalledTimes(1);
    const [state] = historyAdapter.replaceState.mock.calls[0];
    expect(state.navIndex).toBe(1);
    expect(state.entry).toEqual({ page: 'projects', sourceTab: 'shared' });
  });

  it('popstate after replace returns to the entry below, not a stale tab flip', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navPush({ page: 'projects', sourceTab: 'local' }); });
    act(() => { result.current.navReplace({ page: 'projects', sourceTab: 'shared' }); });

    act(() => {
      window.dispatchEvent(Object.assign(new Event('popstate'), { state: { navIndex: 0 } }));
    });

    expect(result.current.navStack).toHaveLength(1);
    expect(result.current.navStack[0].page).toBe('overview');
  });
});

describe('useNavStack navSwapAt (breadcrumb sibling swaps)', () => {
  let historyAdapter;

  beforeEach(() => {
    historyAdapter = {
      pushState: vi.fn(),
      replaceState: vi.fn(),
      back: vi.fn(),
      go: vi.fn(),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // The top-entry swap (switching dimension while ON the dimension page) runs
  // in a transition since the nav-pending-feedback work — these pin that the
  // swap still lands, replaces instead of pushing, and stays StrictMode-pure.
  it('swaps the top entry in place via replaceState, exactly once in StrictMode', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navPush({ page: 'explorer', dimension: 'security' }); });
    historyAdapter.pushState.mockClear();
    historyAdapter.replaceState.mockClear();

    act(() => { result.current.navSwapAt(1, { page: 'explorer', dimension: 'maintainability' }); });

    expect(result.current.navStack).toHaveLength(2);
    expect(result.current.navStack.at(-1).dimension).toBe('maintainability');
    expect(historyAdapter.pushState).not.toHaveBeenCalled();
    expect(historyAdapter.replaceState).toHaveBeenCalledTimes(1);
    expect(result.current.navPending).toBe(false);
  });

  it('swaps an ancestor entry, truncates deeper entries, and walks history back', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navPush({ page: 'explorer', dimension: 'security' }); });
    act(() => { result.current.navPush({ page: 'evalprinciple' }); });
    historyAdapter.go.mockClear();

    act(() => { result.current.navSwapAt(1, { page: 'explorer', dimension: 'maintainability' }); });

    expect(result.current.navStack).toHaveLength(2);
    expect(result.current.navStack.at(-1).dimension).toBe('maintainability');
    expect(historyAdapter.go).toHaveBeenCalledTimes(1);
    expect(historyAdapter.go).toHaveBeenCalledWith(-1);
  });
});

describe('useNavStack navPending', () => {
  let historyAdapter;

  beforeEach(() => {
    historyAdapter = {
      pushState: vi.fn(),
      replaceState: vi.fn(),
      back: vi.fn(),
      go: vi.fn(),
    };
  });

  it('exposes a boolean pending flag that settles false after a push', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );
    expect(result.current.navPending).toBe(false);

    act(() => { result.current.navPush({ page: 'evalprinciple' }); });

    // act() flushes the transition; the navigation itself must have landed.
    expect(result.current.navPending).toBe(false);
    expect(result.current.navStack.at(-1).page).toBe('evalprinciple');
  });
});
