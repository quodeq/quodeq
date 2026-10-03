import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectsKeys } from '../api/queryKeys.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';
import { useCloneStatus } from './useCloneStatus.js';
import { useCloneTransitions } from './useCloneTransitions.js';

const running = { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 10 };
const done = (finishedAt) => ({ state: 'done', phase: SYNC_PHASE.DONE, finishedAt });

function setup(hook, statuses) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, 'invalidateQueries');
  let i = 0; // each poll takes the next status; the last one repeats
  const api = { getCloneStatus: vi.fn(async () => statuses[Math.min(i++, statuses.length - 1)]) };
  const wrapper = ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>;
  return { qc, spy, api, ...renderHook(hook, { wrapper }) };
}

const listCalls = (spy) => spy.mock.calls.filter(([a]) => JSON.stringify(a.queryKey) === JSON.stringify(projectsKeys.list())).length;
const poller = () => useCloneTransitions({ activeMs: 10, idleMs: 500 });
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

describe('useCloneTransitions', () => {
  it('polls fast while downloading and invalidates the project list once on DONE', async () => {
    const { spy, api } = setup(poller, [running, running, running, running, done(1)]);
    await waitFor(() => expect(api.getCloneStatus.mock.calls.length).toBeGreaterThanOrEqual(5), { timeout: 1000 });
    await waitFor(() => expect(listCalls(spy)).toBe(1));
    await pause(60);
    expect(listCalls(spy)).toBe(1);
  });

  it('two DONE snapshots with different finishedAt invalidate twice', async () => {
    const { spy } = setup(() => useCloneTransitions({ activeMs: 10, idleMs: 10 }), [done(1), done(2), done(2)]);
    await waitFor(() => expect(listCalls(spy)).toBe(2), { timeout: 1500 });
  });

  it('a slot that stays done fires once', async () => {
    const { spy, api } = setup(poller, [done(1), done(1)]);
    await waitFor(() => expect(listCalls(spy)).toBe(1));
    expect(api.getCloneStatus).toHaveBeenCalledTimes(1);
  });

  it('a rejected status does not throw and invalidates nothing', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const spy = vi.spyOn(qc, 'invalidateQueries');
    const api = { getCloneStatus: vi.fn(async () => { throw new Error('boom'); }) };
    const wrapper = ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>;
    const { result } = renderHook(() => { poller(); return useCloneStatus(); }, { wrapper });
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalled());
    expect(result.current.active).toBe(false);
    expect(listCalls(spy)).toBe(0);
  });
});

describe('useCloneStatus', () => {
  it('reads the slot without polling on its own', async () => {
    const { api, result } = setup(() => useCloneStatus(), [running]);
    await waitFor(() => expect(result.current.active).toBe(true));
    await pause(80);
    expect(api.getCloneStatus).toHaveBeenCalledTimes(1);
    expect(result.current).toMatchObject({ failed: false, done: false });
  });

  it('flags done and failed', async () => {
    const a = setup(() => useCloneStatus(), [done(1)]);
    await waitFor(() => expect(a.result.current.done).toBe(true));
    const b = setup(() => useCloneStatus(), [{ state: 'error', phase: SYNC_PHASE.ERROR }]);
    await waitFor(() => expect(b.result.current.failed).toBe(true));
  });
});
