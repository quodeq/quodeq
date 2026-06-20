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

describe('useNavStack navPush purity (#363)', () => {
  let pushStateCalls;
  let historyAdapter;

  beforeEach(() => {
    pushStateCalls = [];
    historyAdapter = {
      pushState: vi.fn((...args) => pushStateCalls.push(args)),
      replaceState: vi.fn(),
      back: vi.fn(),
      go: vi.fn(),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls history.pushState exactly once per navPush call even in StrictMode', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    // React StrictMode double-invokes the updater fn passed to setState.
    // If pushState is inside the updater, it fires twice.
    act(() => {
      result.current.navPush({ page: 'settings' });
    });

    // Must be exactly 1, even under double-invoke.
    expect(pushStateCalls).toHaveLength(1);
  });

  it('navStack grows by exactly one entry per navPush in StrictMode', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );
    const initialLength = result.current.navStack.length;

    act(() => { result.current.navPush({ page: 'project' }); });
    expect(result.current.navStack).toHaveLength(initialLength + 1);

    act(() => { result.current.navPush({ page: 'detail' }); });
    expect(result.current.navStack).toHaveLength(initialLength + 2);

    // 2 pushes = 2 pushState calls. In buggy code, double-invoke gives 4.
    expect(pushStateCalls).toHaveLength(2);
  });
});

/**
 * Finding #363 follow-up: navReset and navTab had the identical bug —
 * history.go() called inside the setNavStack updater, causing double-fire
 * under React Strict Mode's double-invocation.
 *
 * Fix: read stepsBack from navStackRef.current before calling setNavStack,
 * then call history.go() as a separate statement outside the updater.
 */
describe('useNavStack navReset purity (#363 follow-up)', () => {
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

  it('calls history.go exactly once per navReset call even in StrictMode', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    // Push two entries so navReset has history entries to go back through.
    act(() => { result.current.navPush({ page: 'a' }); });
    act(() => { result.current.navPush({ page: 'b' }); });
    historyAdapter.go.mockClear();

    act(() => { result.current.navReset(); });

    // Must be exactly 1, not 2 from double-invoke.
    expect(historyAdapter.go).toHaveBeenCalledTimes(1);
    expect(historyAdapter.go).toHaveBeenCalledWith(-2);
  });

  it('resets navStack to single default entry in StrictMode', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navPush({ page: 'settings' }); });
    act(() => { result.current.navReset(); });

    expect(result.current.navStack).toHaveLength(1);
    expect(result.current.navStack[0].page).toBe('overview');
  });

  it('does not call history.go when stack is already at root', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );
    historyAdapter.go.mockClear();

    act(() => { result.current.navReset(); });

    expect(historyAdapter.go).not.toHaveBeenCalled();
  });
});

describe('useNavStack navTab purity (#363 follow-up)', () => {
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

  it('calls history.go exactly once per navTab call even in StrictMode', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    // Push entries so there is history to go back through.
    act(() => { result.current.navPush({ page: 'settings' }); });
    act(() => { result.current.navPush({ page: 'detail' }); });
    historyAdapter.go.mockClear();

    act(() => { result.current.navTab('projects'); });

    // Must be exactly 1, not 2 from double-invoke.
    expect(historyAdapter.go).toHaveBeenCalledTimes(1);
    expect(historyAdapter.go).toHaveBeenCalledWith(-2);
  });

  it('resets navStack to single tab entry in StrictMode', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => { result.current.navPush({ page: 'settings' }); });
    act(() => { result.current.navTab('projects'); });

    expect(result.current.navStack).toHaveLength(1);
    expect(result.current.navStack[0].page).toBe('projects');
  });

  it('increments _tabKey when navigating to the same tab', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    // Start at 'overview' (the default). Navigate to the same tab.
    const initialKey = result.current.navStack[0]._tabKey || 0;
    act(() => { result.current.navTab('overview'); });

    expect(result.current.navStack[0]._tabKey).toBe(initialKey + 1);
  });

  it('does not call history.go when stack is already at root', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );
    historyAdapter.go.mockClear();

    act(() => { result.current.navTab('projects'); });

    expect(historyAdapter.go).not.toHaveBeenCalled();
  });
});
