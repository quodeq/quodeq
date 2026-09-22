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


// Split from useNavStack.test.jsx: history-state payload stripping
// (heavy entry payloads kept out of history.state, recovered from
// memory or the stripped state on popstate).

describe('useNavStack history-state payload stripping', () => {
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

  // pushState structured-clones its state argument synchronously on the main
  // thread. Entries like evalprinciple/file carry a run's whole findings
  // graph (megabytes of violation text), so cloning it inside the click
  // handler froze navigation before React could render anything.
  it('keeps object payloads out of history state, scalars and scalar arrays in', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    const heavy = {
      page: 'evalprinciple',
      sourceTab: 'violations',
      severity: 'major',
      preselectDims: ['security', 'usability'],
      evalPrincipal: { principle: 'p', dimViolations: [{ file: 'a.py', reason: 'x'.repeat(100) }] },
    };
    act(() => { result.current.navPush(heavy); });

    const [state] = historyAdapter.pushState.mock.calls[0];
    expect(state.entry).toEqual({
      page: 'evalprinciple',
      sourceTab: 'violations',
      severity: 'major',
      preselectDims: ['security', 'usability'],
    });
    // The React stack keeps the full entry.
    expect(result.current.navStack.at(-1).evalPrincipal).toBe(heavy.evalPrincipal);
  });

  it('restores the full entry (payload included) on forward popstate', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    const payload = { principle: 'p', dimViolations: [{ file: 'a.py' }] };
    act(() => { result.current.navPush({ page: 'evalprinciple', evalPrincipal: payload }); });

    // Back to root…
    act(() => {
      window.dispatchEvent(Object.assign(new Event('popstate'), { state: { navIndex: 0 } }));
    });
    expect(result.current.navStack).toHaveLength(1);

    // …then Forward: the browser hands back the stripped entry, the hook
    // must recover the full one from memory.
    act(() => {
      window.dispatchEvent(Object.assign(new Event('popstate'), {
        state: { navIndex: 1, entry: { page: 'evalprinciple' } },
      }));
    });
    expect(result.current.navStack).toHaveLength(2);
    expect(result.current.navStack.at(-1).evalPrincipal).toBe(payload);
  });

  it('falls back to the history-state entry when memory has no record (post-reload forward)', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    act(() => {
      window.dispatchEvent(Object.assign(new Event('popstate'), {
        state: { navIndex: 1, entry: { page: 'explorer', dimension: 'security' } },
      }));
    });
    expect(result.current.navStack).toHaveLength(2);
    expect(result.current.navStack.at(-1)).toEqual({ page: 'explorer', dimension: 'security' });
  });

  it('a push after back overwrites the remembered forward entry', () => {
    const { result } = renderHook(
      () => useNavStack({ historyAdapter }),
      { wrapper: strictWrapper },
    );

    const first = { page: 'evalprinciple', evalPrincipal: { principle: 'first' } };
    const second = { page: 'evalprinciple', evalPrincipal: { principle: 'second' } };
    act(() => { result.current.navPush(first); });
    act(() => {
      window.dispatchEvent(Object.assign(new Event('popstate'), { state: { navIndex: 0 } }));
    });
    act(() => { result.current.navPush(second); });
    act(() => {
      window.dispatchEvent(Object.assign(new Event('popstate'), { state: { navIndex: 0 } }));
    });
    act(() => {
      window.dispatchEvent(Object.assign(new Event('popstate'), {
        state: { navIndex: 1, entry: { page: 'evalprinciple' } },
      }));
    });
    expect(result.current.navStack.at(-1).evalPrincipal.principle).toBe('second');
  });
});
