import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectsKeys, sharedKeys } from '../api/queryKeys.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';
import { useSyncActivity } from './useSyncActivity.js';

const idle = { state: 'idle', phase: null };
const base = { configured: true, url: 'u', lastSynced: 1, syncing: false, connect: idle, refresh: idle, pull: idle };

// `status` is one snapshot, or a list the polls walk through (the last one repeats).
function setup(status, clone) {
  const statuses = Array.isArray(status) ? status : [status];
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const api = {
    getSyncStatus: vi.fn(async () => (statuses.length > 1 ? statuses.shift() : statuses[0])),
    getCloneStatus: vi.fn(async () => clone ?? { state: 'idle', phase: null }),
  };
  const wrapper = ({ children }) => (
    <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>
  );
  return { qc, api, ...renderHook(() => useSyncActivity({ activeMs: 10 }), { wrapper }) };
}

describe('useSyncActivity', () => {
  it('is true while a connect reads projects and false once idle', async () => {
    const reading = { ...base, connect: { state: 'running', phase: SYNC_PHASE.READING, projectsFound: 3 } };
    const { qc, result } = setup(reading);
    await waitFor(() => expect(result.current).toBe(true));
    qc.setQueryData(sharedKeys.status(), base);
    await waitFor(() => expect(result.current).toBe(false));
  });

  it('is true while a refresh downloads', async () => {
    const updating = { ...base, refresh: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 10 } };
    const { result } = setup(updating);
    await waitFor(() => expect(result.current).toBe(true));
  });

  it('does not poll while nothing is running', async () => {
    const { api, result } = setup(base);
    await waitFor(() => expect(result.current).toBe(false));
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(api.getSyncStatus).toHaveBeenCalledTimes(1);
  });

  it('is true with an idle shared status and a downloading clone, and false once it is done', async () => {
    const { qc, result } = setup(base, { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 5 });
    await waitFor(() => expect(result.current).toBe(true));
    qc.setQueryData(projectsKeys.clone(), { state: 'done', phase: SYNC_PHASE.DONE, finishedAt: 1 });
    await waitFor(() => expect(result.current).toBe(false));
  });

  // The strip's poll lives on the Repositories tab only; away from it this
  // observer must see the job end by itself, or the hairline never stops.
  it('polls on its own while a job runs and stops once it is done', async () => {
    const reading = { ...base, connect: { state: 'running', phase: SYNC_PHASE.READING, projectsFound: 3 } };
    const done = { ...base, connect: { state: 'done', phase: SYNC_PHASE.DONE, projectsFound: 5 } };
    // Enough "reading" polls that the first assertion catches the active state before "done" lands.
    const { api, result } = setup([reading, reading, reading, reading, reading, reading, reading, reading, done]);
    await waitFor(() => expect(result.current).toBe(true));
    await waitFor(() => expect(result.current).toBe(false));
    const callsWhenDone = api.getSyncStatus.mock.calls.length;
    expect(callsWhenDone).toBeGreaterThanOrEqual(3);
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(api.getSyncStatus).toHaveBeenCalledTimes(callsWhenDone);
  });
});
