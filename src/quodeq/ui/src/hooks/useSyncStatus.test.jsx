import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectsKeys, sharedKeys } from '../api/queryKeys.js';
import { useSyncStatus } from './useSyncStatus.js';

const idle = { state: 'idle', phase: null };
const base = { configured: true, url: 'u', lastSynced: 1, syncing: false, connect: idle, refresh: idle, pull: idle };

function setup(statuses, opts) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, 'invalidateQueries');
  let i = 0; // each poll takes the next status; the last one repeats
  const api = { getSyncStatus: vi.fn(async () => statuses[Math.min(i++, statuses.length - 1)]) };
  const wrapper = ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>;
  return { spy, api, ...renderHook(() => useSyncStatus({ activeMs: 5, idleMs: 50, ...opts }), { wrapper }) };
}

const keyCalls = (spy, key) => spy.mock.calls.filter(([a]) => JSON.stringify(a.queryKey) === JSON.stringify(key)).length;

describe('useSyncStatus', () => {
  it('invalidates the shared list on each reading tick and once on done, plus projects on connect done', async () => {
    const reading = { ...base, connect: { state: 'running', phase: 'reading', projectsFound: 2 } };
    const done = { ...base, connect: { state: 'done', phase: 'done', projectsFound: 5 } };
    const { spy } = setup([reading, reading, done, done]);
    await waitFor(() => expect(spy.mock.calls.filter(([a]) => a.queryKey?.[1] === 'list' && a.queryKey?.[0] === 'shared').length).toBeGreaterThanOrEqual(3));
    await waitFor(() => expect(spy.mock.calls.some(([a]) => JSON.stringify(a.queryKey) === JSON.stringify(projectsKeys.list()))).toBe(true));
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
    await waitFor(() => expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(3), { timeout: 500 });
    expect(keyCalls(spy, sharedKeys.list())).toBe(1);
    expect(keyCalls(spy, projectsKeys.list())).toBe(0);
  });

  it('a slot that stays done across polls fires its transition once', async () => {
    const done = { ...base, connect: { state: 'done', phase: 'done' } };
    const { spy, api } = setup([done, done, done]);
    await waitFor(() => expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(3), { timeout: 500 });
    expect(keyCalls(spy, projectsKeys.list())).toBe(1);
  });

  it('exposes configured, url, lastSynced and the three slots', async () => {
    const { result } = setup([base]);
    await waitFor(() => expect(result.current.configured).toBe(true));
    expect(result.current).toMatchObject({ url: 'u', lastSynced: 1, connect: idle, refresh: idle, pull: idle, active: false });
  });
});
