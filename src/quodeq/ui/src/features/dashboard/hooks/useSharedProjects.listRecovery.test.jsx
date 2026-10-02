import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useSharedProjects } from './useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

// A first listing of a fresh clone can outlast the request timeout. The
// strip then shows "couldn't load"; these pin that the list itself recovers,
// through the strip's retry and through the next DONE edge, without a reload.

const URL = 'https://github.com/team/results.git';
const idle = { state: 'idle', phase: null };
const statusOf = (refresh = idle) => ({ configured: true, url: URL, connect: idle, refresh, pull: idle });
const LISTED = { projects: [{ id: 'p1', name: 'demo' }], lastSynced: null, stale: false };

function render(api) {
  const QC = withQueryClient();
  const wrapper = ({ children }) => <QC><ApiProvider value={api}>{children}</ApiProvider></QC>;
  return renderHook(() => useSharedProjects(), { wrapper });
}

function api({ getSyncStatus, startRefresh = vi.fn(async () => ({ started: true })) }) {
  const sharedListProjects = vi.fn()
    .mockRejectedValueOnce(new Error('Request timed out'))
    .mockResolvedValue(LISTED);
  return { getSyncStatus, sharedListProjects, startRefresh, connectShared: vi.fn(), startPull: vi.fn() };
}

describe('useSharedProjects list recovery', () => {
  it('a refresh DONE edge refetches a list that errored', async () => {
    let phase = 'idle';
    const getSyncStatus = vi.fn(async () => {
      if (phase === 'idle') return statusOf();
      if (phase === 'running') { phase = 'done'; return statusOf({ state: 'running', phase: 'downloading' }); }
      return statusOf({ state: 'done', phase: 'done' });
    });
    const fake = api({ getSyncStatus });
    const { result } = render(fake);
    await waitFor(() => expect(result.current.error).toBe('Request timed out'));
    phase = 'running';
    await act(async () => { await result.current.refresh(); });
    await waitFor(() => expect(result.current.projects).toHaveLength(1), { timeout: 4000 });
    expect(result.current.error).toBeNull();
  });

  it('retry refetches the errored list even when the refresh cannot start', async () => {
    const getSyncStatus = vi.fn(async () => statusOf());
    const startRefresh = vi.fn(async () => { throw new Error('boom'); });
    const fake = api({ getSyncStatus, startRefresh });
    const { result } = render(fake);
    await waitFor(() => expect(result.current.error).toBe('Request timed out'));
    await act(async () => { await result.current.refresh(); });
    await waitFor(() => expect(result.current.projects).toHaveLength(1));
    expect(fake.sharedListProjects).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
  });
});
