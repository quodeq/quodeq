import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSharedActions } from './useSharedActions.js';

describe('useSharedActions', () => {
  it('connect resolves after the one PUT and touches nothing else', async () => {
    const connectShared = vi.fn(async (url) => ({ started: true, url }));
    const { result } = renderHook(() => useSharedActions({ connectShared, startPull: vi.fn() }));

    await act(async () => { await result.current.connect('https://github.com/t/r.git'); });

    expect(connectShared).toHaveBeenCalledTimes(1);
    expect(connectShared).toHaveBeenCalledWith('https://github.com/t/r.git');
    expect(result.current.connecting).toBe(false);
    expect(result.current.connectError).toBeNull();
  });

  it('connect keeps a failure to start as connectError', async () => {
    const connectShared = vi.fn(async () => { throw new Error('a connect is already running'); });
    const { result } = renderHook(() => useSharedActions({ connectShared, startPull: vi.fn() }));

    await act(async () => { await result.current.connect('x'); });

    expect(result.current.connectError).toBe('a connect is already running');
  });

  it('connect keeps an ACCESS_ refusal as accessFailure (the access panel envelope), not as connectError', async () => {
    const refusal = Object.assign(new Error('auth required'), {
      code: 'ACCESS_AUTH_REQUIRED', body: { kind: 'auth_required', host: 'github.com', isGitHub: true },
    });
    const connectShared = vi.fn(async () => { throw refusal; });
    const { result } = renderHook(() => useSharedActions({ connectShared, startPull: vi.fn() }));

    await act(async () => { await result.current.connect('x'); });

    expect(result.current.connectError).toBeNull();
    expect(result.current.accessFailure).toEqual({ kind: 'auth_required', detail: '', host: 'github.com', isGitHub: true, cloneUrl: '' });

    // The next attempt clears it.
    connectShared.mockResolvedValueOnce({ started: true });
    await act(async () => { await result.current.connect('x'); });
    expect(result.current.accessFailure).toBeNull();
  });

  it('pull passes the project and action to startPull and returns its answer', async () => {
    const startPull = vi.fn(async (project) => ({ started: true, project }));
    const { result } = renderHook(() => useSharedActions({ connectShared: vi.fn(), startPull }));

    let answer;
    await act(async () => { answer = await result.current.pull('p1', 'copy'); });

    expect(startPull).toHaveBeenCalledWith('p1', 'copy');
    expect(answer).toEqual({ started: true, project: 'p1' });
  });
});
