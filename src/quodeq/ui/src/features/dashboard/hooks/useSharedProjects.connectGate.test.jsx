import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useSharedContentSignal, useSharedProjects } from './useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

// The settings are written before a connect job hydrates the listing, so the
// status says `configured` while the connect is still READING. A list request
// then runs the same cold hydration as the job, concurrently; the list waits
// for the connect to finish and the DONE edge (or the enable) fetches it once.

const URL = 'https://github.com/team/results.git';
const idle = { state: 'idle', phase: null };
const withConnect = (connect) => ({ configured: true, url: URL, connect, refresh: idle, pull: idle });
const READING = withConnect({ state: 'running', phase: 'reading', projectsFound: 1 });
const DONE = withConnect({ state: 'done', phase: 'done', projectsFound: 1 });
const LISTED = { projects: [{ id: 'p1', name: 'demo' }], lastSynced: null, stale: false };

function render(hook, api) {
  const QC = withQueryClient();
  const wrapper = ({ children }) => <QC><ApiProvider value={api}>{children}</ApiProvider></QC>;
  return renderHook(hook, { wrapper });
}

function fakeApi(getStatus) {
  const sharedListProjects = vi.fn(async () => LISTED);
  return {
    getSyncStatus: getStatus, getSharedStatus: getStatus, sharedListProjects,
    startRefresh: vi.fn(), connectShared: vi.fn(), startPull: vi.fn(),
  };
}

describe('the shared list waits for a connect to finish reading', () => {
  it('fetches the list exactly once, after the connect reaches DONE', async () => {
    let polls = 0;
    const listCallsAtPoll = [];
    const api = fakeApi(vi.fn(async () => {
      polls += 1;
      listCallsAtPoll.push(api.sharedListProjects.mock.calls.length);
      return polls <= 2 ? READING : DONE;
    }));
    const { result } = render(() => useSharedProjects(), api);
    await waitFor(() => expect(result.current.projects).toHaveLength(1), { timeout: 4000 });
    expect(api.sharedListProjects).toHaveBeenCalledTimes(1);
    expect(listCallsAtPoll.slice(0, 3)).toEqual([0, 0, 0]); // nothing listed until the DONE poll landed
  });

  it('the content signal stays unsettled while the connect reads', async () => {
    const api = fakeApi(vi.fn(async () => READING));
    const { result } = render(() => useSharedContentSignal(), api);
    await waitFor(() => expect(api.getSharedStatus).toHaveBeenCalled());
    await new Promise((resolve) => { setTimeout(resolve, 50); });
    expect(result.current).toEqual({ settled: false, hasContent: false, publishedCount: 0 });
    expect(api.sharedListProjects).not.toHaveBeenCalled();
  });
});
