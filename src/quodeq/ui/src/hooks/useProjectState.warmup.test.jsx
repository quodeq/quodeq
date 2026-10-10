import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectsKeys } from '../api/queryKeys.js';
import { useProjectState } from './useProjectState.js';

function setup(listProjects) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }) => createElement(
    QueryClientProvider, { client }, createElement(ApiProvider, { value: { listProjects } }, children),
  );
  const storage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  return { client, wrapper, storage };
}

describe('useProjectState: the warm-up snapshot rides on the list', () => {
  it('records the snapshot the list response carried, and the list stays a plain array', async () => {
    const warmup = { active: true, projectsDone: 1, projectsTotal: 3, currentProjectName: 'quodeq' };
    const { client, wrapper, storage } = setup(vi.fn().mockResolvedValue({
      projects: [{ id: 'p1', name: 'p1', summaryPending: true }], warmup,
    }));
    const { result } = renderHook(() => useProjectState({ storage, summaryPollMs: 60000 }), { wrapper });
    await waitFor(() => expect(result.current.projectsLoaded).toBe(true));
    expect(result.current.projects.map((p) => p.id)).toEqual(['p1']);
    expect(client.getQueryData(projectsKeys.warmup())).toEqual(warmup);
  });

  it('a response without a snapshot records null', async () => {
    const { client, wrapper, storage } = setup(vi.fn().mockResolvedValue({ projects: [] }));
    const { result } = renderHook(() => useProjectState({ storage }), { wrapper });
    await waitFor(() => expect(result.current.projectsLoaded).toBe(true));
    expect(client.getQueryData(projectsKeys.warmup())).toBeNull();
  });
});
