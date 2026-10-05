import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useSharedProjects } from './useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

// The server lists a shared card only once the project is fully warmed and
// counts the rest in `warmup`; the page shows one placeholder per card still
// being warmed, so a team's results arrive one by one instead of all at once.
function makeFakeApi(listing) {
  const api = {
    getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
    sharedListProjects: vi.fn(async () => listing),
    connectShared: vi.fn(), startRefresh: vi.fn(), startPull: vi.fn(),
  };
  return { getSyncStatus: (...a) => api.getSharedStatus(...a), ...api };
}

function wrap(fakeApi, children) {
  const QC = withQueryClient();
  return (
    <QC>
      <ApiProvider value={fakeApi}>{children}</ApiProvider>
    </QC>
  );
}

describe('useSharedProjects warming', () => {
  it('counts the cards the server is still warming', async () => {
    const fakeApi = makeFakeApi({
      projects: [{ id: 'p1', name: 'demo' }],
      warmup: { active: true, projectsDone: 1, projectsTotal: 4, currentProjectName: 'two' },
    });
    const { result } = renderHook(() => useSharedProjects(), { wrapper: ({ children }) => wrap(fakeApi, children) });
    await waitFor(() => expect(result.current.projects).toHaveLength(1));
    expect(result.current.warming).toEqual({ active: true, done: 1, total: 4, remaining: 3 });
  });

  it('is idle when the listing carries no warm-up or a finished one', async () => {
    const fakeApi = makeFakeApi({ projects: [{ id: 'p1', name: 'demo' }], warmup: { active: false, projectsDone: 2, projectsTotal: 2 } });
    const { result } = renderHook(() => useSharedProjects(), { wrapper: ({ children }) => wrap(fakeApi, children) });
    await waitFor(() => expect(result.current.projects).toHaveLength(1));
    expect(result.current.warming).toEqual({ active: false, done: 2, total: 2, remaining: 0 });

    const bare = makeFakeApi({ projects: [] });
    const { result: bareResult } = renderHook(() => useSharedProjects(), { wrapper: ({ children }) => wrap(bare, children) });
    await waitFor(() => expect(bareResult.current.loading).toBe(false));
    expect(bareResult.current.warming).toEqual({ active: false, done: 0, total: 0, remaining: 0 });
  });
});
