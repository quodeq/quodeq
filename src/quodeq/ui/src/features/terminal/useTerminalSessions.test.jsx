import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../api/ApiContext.jsx';
import { useTerminalSessions } from './useTerminalSessions.js';

function makeWrapper(fakeApi) {
  return function Wrapper({ children }) {
    return <ApiProvider value={fakeApi}>{children}</ApiProvider>;
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((res) => { resolve = res; });
  return { promise, resolve };
}

describe('useTerminalSessions', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  // reconcilingRef serializes concurrent reconciles: a server restart can
  // make every open socket report 'gone' in the same tick, and each one
  // calls reconcile(). Without the guard that would fan out into N parallel
  // list/create cycles (and N extra creates past the empty-list check).
  it('a burst of concurrent reconciles shares one fetch/create cycle and one re-render', async () => {
    const firstList = deferred();
    const fakeApi = {
      listTerminalSessions: vi.fn()
        .mockImplementationOnce(() => firstList.promise)
        .mockResolvedValue({ sessions: [{ id: 's1', name: 'zsh · 1', alive: true, cwd: '~' }], max: 6 }),
      createTerminalSession: vi.fn().mockResolvedValue({ id: 's1', name: 'zsh · 1' }),
      killTerminalSession: vi.fn().mockResolvedValue({ ok: true }),
    };

    let renderCount = 0;
    const { result } = renderHook(() => {
      renderCount += 1;
      return useTerminalSessions({ enabled: false });
    }, { wrapper: makeWrapper(fakeApi) });

    expect(renderCount).toBe(1);

    // N independent sockets ('gone' events) all ask for a reconcile in the
    // same tick, before the in-flight list call has resolved.
    let p1, p2, p3;
    act(() => {
      p1 = result.current.reconcile();
      p2 = result.current.reconcile();
      p3 = result.current.reconcile();
    });

    // All three calls observed the same in-flight operation instead of each
    // starting its own.
    expect(p1).toBe(p2);
    expect(p2).toBe(p3);
    expect(fakeApi.listTerminalSessions).toHaveBeenCalledTimes(1);
    expect(fakeApi.createTerminalSession).not.toHaveBeenCalled();
    // Nothing has resolved yet, so nothing has re-rendered yet either.
    expect(renderCount).toBe(1);

    await act(async () => {
      // The list comes back empty (every session really did die) — this is
      // what would fan out into 3 creates without the serialization guard.
      firstList.resolve({ sessions: [], max: 6 });
      await Promise.all([p1, p2, p3]);
    });

    // Exactly one create for the whole burst, not one per reconcile() call.
    expect(fakeApi.createTerminalSession).toHaveBeenCalledTimes(1);
    expect(fakeApi.listTerminalSessions).toHaveBeenCalledTimes(2);
    expect(result.current.sessions).toEqual([
      { id: 's1', name: 'zsh · 1', alive: true, cwd: '~' },
    ]);
    expect(result.current.activeId).toBe('s1');
    // The burst settled through ONE async execution whose state updates
    // (setSessions/setMax/setActiveId) batch into a single commit — not
    // one render per reconcile() call in the burst.
    expect(renderCount).toBe(2);
  });

  it('does not create a session when the reconciled list is non-empty', async () => {
    const fakeApi = {
      listTerminalSessions: vi.fn().mockResolvedValue({ sessions: [{ id: 's1' }], max: 6 }),
      createTerminalSession: vi.fn().mockResolvedValue({ id: 's1' }),
      killTerminalSession: vi.fn().mockResolvedValue({ ok: true }),
    };
    const { result } = renderHook(() => useTerminalSessions({ enabled: false }), {
      wrapper: makeWrapper(fakeApi),
    });

    await act(async () => { await result.current.reconcile(); });
    expect(fakeApi.createTerminalSession).not.toHaveBeenCalled();
    expect(result.current.sessions).toEqual([{ id: 's1' }]);
  });

  it('a reconcile after the previous one settles starts a fresh fetch', async () => {
    const fakeApi = {
      listTerminalSessions: vi.fn().mockResolvedValue({ sessions: [{ id: 's1' }], max: 6 }),
      createTerminalSession: vi.fn().mockResolvedValue({ id: 's1' }),
      killTerminalSession: vi.fn().mockResolvedValue({ ok: true }),
    };
    const { result } = renderHook(() => useTerminalSessions({ enabled: false }), {
      wrapper: makeWrapper(fakeApi),
    });

    await act(async () => { await result.current.reconcile(); });
    expect(fakeApi.listTerminalSessions).toHaveBeenCalledTimes(1);
    await act(async () => { await result.current.reconcile(); });
    expect(fakeApi.listTerminalSessions).toHaveBeenCalledTimes(2);
  });

  it('logs and keeps current tabs when the session list is unreachable', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    const fakeApi = {
      listTerminalSessions: vi.fn().mockRejectedValue(new Error('network down')),
      createTerminalSession: vi.fn(),
      killTerminalSession: vi.fn(),
    };
    const { result } = renderHook(() => useTerminalSessions({ enabled: false }), {
      wrapper: makeWrapper(fakeApi),
    });

    await act(async () => { await result.current.reconcile(); });

    // The current (empty) tabs are kept, not cleared, on an unreachable server.
    expect(result.current.sessions).toEqual([]);
    expect(debugSpy).toHaveBeenCalledWith(
      expect.stringContaining('reconcile list unreachable'),
      expect.any(Error),
    );
    warnSpy.mockRestore();
    debugSpy.mockRestore();
  });

  it('logs when the create-if-empty call fails, distinct from the list-unreachable case', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const fakeApi = {
      listTerminalSessions: vi.fn()
        .mockResolvedValueOnce({ sessions: [], max: 6 })
        .mockResolvedValue({ sessions: [], max: 6 }),
      createTerminalSession: vi.fn().mockRejectedValue(new Error('create failed')),
      killTerminalSession: vi.fn(),
    };
    const { result } = renderHook(() => useTerminalSessions({ enabled: false }), {
      wrapper: makeWrapper(fakeApi),
    });

    await act(async () => { await result.current.reconcile(); });

    expect(fakeApi.createTerminalSession).toHaveBeenCalledTimes(1);
    // The list call ran twice (initial + create-if-empty re-list), so this
    // reached setSessions/setActiveId rather than bailing out as "unreachable".
    expect(fakeApi.listTerminalSessions).toHaveBeenCalledTimes(2);
    expect(result.current.sessions).toEqual([]);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('create-if-empty session failed'),
      expect.any(Error),
    );
    warnSpy.mockRestore();
  });

  it('logs when killing a closed session fails, after the tab is already dropped locally', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    // closeSession awaits the rejected kill (and its warn) before calling
    // reconcile() again; keep that follow-up list call in-flight so the
    // local removal + warning can be observed independent of the resync.
    const secondList = deferred();
    const fakeApi = {
      listTerminalSessions: vi.fn()
        .mockResolvedValueOnce({ sessions: [{ id: 's1' }, { id: 's2' }], max: 6 })
        .mockImplementationOnce(() => secondList.promise),
      createTerminalSession: vi.fn(),
      killTerminalSession: vi.fn().mockRejectedValue(new Error('kill failed')),
    };
    const { result } = renderHook(() => useTerminalSessions({ enabled: false }), {
      wrapper: makeWrapper(fakeApi),
    });

    await act(async () => { await result.current.reconcile(); });
    expect(result.current.sessions).toEqual([{ id: 's1' }, { id: 's2' }]);

    act(() => { result.current.closeSession('s1'); });

    // The tab is gone from local state even though the server-side kill
    // rejected: this is exactly the orphan case the warning documents.
    await waitFor(() => {
      expect(result.current.sessions).toEqual([{ id: 's2' }]);
    });
    expect(warnSpy).toHaveBeenCalledWith(
      'terminal: failed to kill session',
      's1',
      expect.any(Error),
    );

    await act(async () => {
      secondList.resolve({ sessions: [{ id: 's1' }, { id: 's2' }], max: 6 });
    });
    warnSpy.mockRestore();
  });
});
