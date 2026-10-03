import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { sharedKeys } from '../api/queryKeys.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';
import { useSyncActivity } from './useSyncActivity.js';

const idle = { state: 'idle', phase: null };
const base = { configured: true, url: 'u', lastSynced: 1, syncing: false, connect: idle, refresh: idle, pull: idle };

function setup(status) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const api = { getSyncStatus: vi.fn(async () => status) };
  const wrapper = ({ children }) => (
    <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>
  );
  return { qc, api, ...renderHook(() => useSyncActivity(), { wrapper }) };
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

  it('does not poll on its own', async () => {
    const { api, result } = setup(base);
    await waitFor(() => expect(result.current).toBe(false));
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(api.getSyncStatus).toHaveBeenCalledTimes(1);
  });
});
