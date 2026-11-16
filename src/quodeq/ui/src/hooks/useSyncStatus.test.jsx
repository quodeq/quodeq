import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectsKeys, sharedKeys, standardsKeys } from '../api/queryKeys.js';
import { useSyncStatus } from './useSyncStatus.js';

const idle = { state: 'idle', phase: null };
const base = { configured: true, url: 'u', lastSynced: 1, syncing: false, connect: idle, refresh: idle, pull: idle };

function setup(statuses, opts, seed) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (seed) seed(qc);
  const spy = vi.spyOn(qc, 'invalidateQueries');
  let i = 0; // each poll takes the next status; the last one repeats
  const api = { getSyncStatus: vi.fn(async () => statuses[Math.min(i++, statuses.length - 1)]) };
  const wrapper = ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>;
  return { spy, api, ...renderHook(() => useSyncStatus({ activeMs: 5, idleMs: 50, ...opts }), { wrapper }) };
}

const keyCalls = (spy, key) => spy.mock.calls.filter(([a]) => JSON.stringify(a.queryKey) === JSON.stringify(key)).length;

describe('useSyncStatus', () => {
  it('leaves the shared list alone while reading and invalidates it once on done, plus projects on connect done', async () => {
    const reading = { ...base, connect: { state: 'running', phase: 'reading', projectsFound: 2 } };
    const done = { ...base, connect: { state: 'done', phase: 'done', projectsFound: 5 } };
    const { spy, api } = setup([reading, reading, reading, done, done]);
    await waitFor(() => {
      expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(5);
      expect(keyCalls(spy, sharedKeys.list())).toBe(1);
      expect(keyCalls(spy, projectsKeys.list())).toBe(1);
    }, { timeout: 500 });
  });

  it('polls fast while active and slow when idle', async () => {
    const active = { ...base, refresh: { state: 'running', phase: 'downloading', percent: 10 } };
    const { api, result } = setup([active, active, active]);
    await waitFor(() => expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(3), { timeout: 500 });
    expect(result.current.active).toBe(true);
  });

  it('pull done invalidates the projects list', async () => {
    const pulling = { ...base, pull: { state: 'running', phase: 'downloading', project: 'a' } };
    const pulled = { ...base, pull: { state: 'done', phase: 'done', project: 'a', projectId: 'x' } };
    const { spy } = setup([pulling, pulled, pulled]);
    await waitFor(() => expect(spy.mock.calls.some(([a]) => JSON.stringify(a.queryKey) === JSON.stringify(projectsKeys.list()))).toBe(true));
  });

  it('a refresh done invalidates the shared list but never the projects list', async () => {
    const running = { ...base, refresh: { state: 'running', phase: 'downloading' } };
    const done = { ...base, refresh: { state: 'done', phase: 'done' } };
    const { spy, api } = setup([running, done, done]);
    await waitFor(() => {
      expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(3);
      expect(keyCalls(spy, sharedKeys.list())).toBe(1);
      expect(keyCalls(spy, projectsKeys.list())).toBe(0);
    }, { timeout: 500 });
  });

  it('a slot already done at mount seeds the baseline and invalidates nothing', async () => {
    const done = { ...base, connect: { state: 'done', phase: 'done' }, refresh: { state: 'done', phase: 'done' } };
    const { spy, api } = setup([done, done, done]);
    await waitFor(() => expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(3), { timeout: 500 });
    expect(spy).not.toHaveBeenCalled();
  });

  it('a slot that stays done after a real transition fires once', async () => {
    const running = { ...base, connect: { state: 'running', phase: 'downloading' } };
    const done = { ...base, connect: { state: 'done', phase: 'done' } };
    const { spy, api } = setup([running, done, done, done]);
    await waitFor(() => {
      expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(4);
      expect(keyCalls(spy, projectsKeys.list())).toBe(1);
    }, { timeout: 500 });
  });

  it('exposes configured, url, lastSynced and the three slots', async () => {
    const { result } = setup([base]);
    await waitFor(() => expect(result.current.configured).toBe(true));
    expect(result.current).toMatchObject({ url: 'u', lastSynced: 1, connect: idle, refresh: idle, pull: idle, active: false });
  });

  it('a connect DONE edge invalidates the projects list exactly once, and so does a pull DONE edge', async () => {
    for (const kind of ['connect', 'pull']) {
      const running = { ...base, [kind]: { state: 'running', phase: 'downloading' } };
      const done = { ...base, [kind]: { state: 'done', phase: 'done' } };
      const { spy, api } = setup([running, done, done, done]);
      await waitFor(() => {
        expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(4);
        expect(keyCalls(spy, projectsKeys.list())).toBe(1);
      }, { timeout: 500 });
    }
  });

  it('two DONE snapshots with different finishedAt are two jobs and invalidate twice', async () => {
    const first = { ...base, pull: { state: 'done', phase: 'done', project: 'a', finishedAt: 10 } };
    const second = { ...base, pull: { state: 'done', phase: 'done', project: 'b', finishedAt: 20 } };
    const { spy, api } = setup([base, first, second, second, second]);
    await waitFor(() => {
      expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(5);
      expect(keyCalls(spy, projectsKeys.list())).toBe(2);
      expect(keyCalls(spy, sharedKeys.list())).toBe(2);
    }, { timeout: 500 });
  });

  it('identical DONE snapshots (same finishedAt) invalidate once', async () => {
    const done = { ...base, pull: { state: 'done', phase: 'done', project: 'a', finishedAt: 10 } };
    const { spy, api } = setup([base, done, { ...done, pull: { ...done.pull } }, done, done]);
    await waitFor(() => {
      expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(5);
      expect(keyCalls(spy, projectsKeys.list())).toBe(1);
    }, { timeout: 500 });
  });

  it('error, done, error, done fires once per DONE edge', async () => {
    const mk = (phase) => ({ ...base, pull: { state: phase, phase } });
    const { spy, api } = setup([mk('error'), mk('done'), mk('error'), mk('done'), mk('done'), mk('done')]);
    await waitFor(() => {
      expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(6);
      expect(keyCalls(spy, projectsKeys.list())).toBe(2);
      expect(keyCalls(spy, sharedKeys.list())).toBe(2);
    }, { timeout: 500 });
  });

  it('a refresh or connect done re-lists the standards (their sync state reads the clone); a pull done does not', async () => {
    for (const [kind, expected] of [['refresh', 1], ['connect', 1], ['pull', 0]]) {
      const running = { ...base, [kind]: { state: 'running', phase: 'downloading' } };
      const done = { ...base, [kind]: { state: 'done', phase: 'done' } };
      const { spy } = setup([running, done, done]);
      // Every kind re-lists the shared list on DONE: proof the edge was handled before reading the standards count.
      await waitFor(() => {
        expect(keyCalls(spy, sharedKeys.list())).toBe(1);
        expect(keyCalls(spy, standardsKeys.list())).toBe(expected);
      }, { timeout: 500 });
    }
  });

  describe('a slot already DONE at the first snapshot', () => {
    const done = { ...base, refresh: { state: 'done', phase: 'done', finishedAt: 100 } };
    const run = async (seed) => {
      const { spy, api } = setup([done, done], undefined, seed);
      await waitFor(() => expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(2), { timeout: 500 });
      return spy;
    };

    it('invalidates a list cached before the job finished', async () => {
      const spy = await run((qc) => {
        qc.setQueryData(sharedKeys.list(), [], { updatedAt: 50000 });
        qc.setQueryData(standardsKeys.list(), [], { updatedAt: 50000 });
      });
      expect(keyCalls(spy, sharedKeys.list())).toBe(1);
      expect(keyCalls(spy, standardsKeys.list())).toBe(1);
    });

    it('leaves a list fetched after the job finished alone', async () => {
      const spy = await run((qc) => {
        qc.setQueryData(sharedKeys.list(), [], { updatedAt: 200000 });
        qc.setQueryData(standardsKeys.list(), [], { updatedAt: 200000 });
      });
      expect(spy).not.toHaveBeenCalled();
    });

    it('leaves a key with no cache alone', async () => {
      const spy = await run(() => {});
      expect(spy).not.toHaveBeenCalled();
    });
  });
});
