import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectsKeys } from '../api/queryKeys.js';
import { useProjectState } from './useProjectState.js';

function setup(api) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>;
  return { qc, ...renderHook(() => useProjectState(), { wrapper }) };
}

// Restored here, not at the end of the test, so a failed assertion in the
// fake-timer poll test cannot leave later tests on fake timers.
afterEach(() => { vi.useRealTimers(); });

describe('useProjectState as a query', () => {
  it('loads once, exposes projectsLoaded, and refetches on invalidation', async () => {
    const lists = [[{ id: 'a', name: 'a' }], [{ id: 'a', name: 'a' }, { id: 'b', name: 'b' }]];
    const listProjects = vi.fn(async () => ({ projects: lists.shift() }));
    const { qc, result } = setup({ listProjects });
    await waitFor(() => expect(result.current.projectsLoaded).toBe(true));
    expect(result.current.projects.map((p) => p.id)).toEqual(['a']);
    await act(async () => { await qc.invalidateQueries({ queryKey: projectsKeys.list() }); });
    await waitFor(() => expect(result.current.projects.map((p) => p.id)).toEqual(['a', 'b']));
    expect(listProjects).toHaveBeenCalledTimes(2);
  });

  it('marks projectsLoadFailed on error and retryLoadProjects refetches', async () => {
    const listProjects = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce({ projects: [] });
    const { result } = setup({ listProjects });
    await waitFor(() => expect(result.current.projectsLoadFailed).toBe(true));
    await act(async () => { await result.current.retryLoadProjects(); });
    await waitFor(() => expect(result.current.projectsLoadFailed).toBe(false));
  });

  it('polls while a summary is pending and stops when it is not', async () => {
    vi.useFakeTimers();
    const answers = [{ projects: [{ id: 'a', summaryPending: true }] }, { projects: [{ id: 'a', summaryPending: false }] }];
    const listProjects = vi.fn(async () => answers.shift() ?? { projects: [{ id: 'a', summaryPending: false }] });
    const { result } = setup({ listProjects });
    await vi.waitFor(() => expect(result.current.projectsLoaded).toBe(true));
    await act(async () => { await vi.advanceTimersByTimeAsync(3100); });
    expect(listProjects).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(6200); });
    expect(listProjects).toHaveBeenCalledTimes(2);
  });

  it('loadProjects invalidates the list and resolves with the refetched projects', async () => {
    const lists = [[{ id: 'a' }], [{ id: 'a' }, { id: 'b' }]];
    const listProjects = vi.fn(async () => ({ projects: lists.shift() }));
    const { result } = setup({ listProjects });
    await waitFor(() => expect(result.current.projectsLoaded).toBe(true));
    let list;
    await act(async () => { list = await result.current.loadProjects(); });
    expect(list.map((p) => p.id)).toEqual(['a', 'b']);
  });

  it('setProjects writes straight into the query cache', async () => {
    const listProjects = vi.fn(async () => ({ projects: [{ id: 'a' }] }));
    const { qc, result } = setup({ listProjects });
    await waitFor(() => expect(result.current.projectsLoaded).toBe(true));
    act(() => { result.current.setProjects([{ id: 'z' }]); });
    expect(qc.getQueryData(projectsKeys.list())).toEqual([{ id: 'z' }]);
    await waitFor(() => expect(result.current.projects.map((p) => p.id)).toEqual(['z']));
  });

  it('a failed first load is not reported as loaded, so nothing reads it as "no projects"', async () => {
    const listProjects = vi.fn().mockRejectedValue(new Error('down'));
    const { result } = setup({ listProjects });
    await waitFor(() => expect(result.current.projectsLoadFailed).toBe(true));
    expect(result.current.projectsLoaded).toBe(false);
  });

  it('two hooks share one list: invalidating from one updates the other', async () => {
    const lists = [[{ id: 'a' }], [{ id: 'a' }, { id: 'b' }]];
    const listProjects = vi.fn(async () => ({ projects: lists.shift() }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={{ listProjects }}>{children}</ApiProvider></QueryClientProvider>;
    const { result } = renderHook(() => ({ one: useProjectState(), two: useProjectState() }), { wrapper });
    await waitFor(() => expect(result.current.two.projectsLoaded).toBe(true));
    await act(async () => { await result.current.one.loadProjects(); });
    await waitFor(() => expect(result.current.two.projects.map((p) => p.id)).toEqual(['a', 'b']));
  });
});
