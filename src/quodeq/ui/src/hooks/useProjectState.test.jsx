import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('../api/index.js', () => ({ listProjects: vi.fn() }));
import { listProjects } from '../api/index.js';
import { useProjectState } from './useProjectState.js';

const noStorage = { getItem: () => '', setItem: () => {} };

beforeEach(() => { listProjects.mockReset(); });

describe('useProjectState — resilience to a transient projects-fetch failure', () => {
  it('does NOT fall to onboarding when the fetch keeps failing (retries, then gives up without onboarding)', async () => {
    listProjects.mockRejectedValue(new DOMException('aborted', 'AbortError'));
    const onNoProjects = vi.fn();
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects, storage: noStorage, retryDelayMs: 0, maxRetries: 2 }));

    // initial attempt + 2 retries = 3 calls
    await waitFor(() => expect(listProjects).toHaveBeenCalledTimes(3));
    await new Promise((r) => setTimeout(r, 0)); // flush the final .catch/.then

    expect(onNoProjects).not.toHaveBeenCalled();       // <-- the bug: today this IS called
    expect(result.current.projectsLoaded).toBe(false); // stays in loading, not a false "loaded/empty"
  });

  it('recovers via retry: a transient failure then success loads projects without onboarding', async () => {
    listProjects
      .mockRejectedValueOnce(new DOMException('aborted', 'AbortError'))
      .mockResolvedValueOnce([{ id: 'p1', name: 'proj1' }]);
    const onNoProjects = vi.fn();
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects, storage: noStorage, retryDelayMs: 0, maxRetries: 3 }));

    await waitFor(() => expect(result.current.projects).toHaveLength(1));
    expect(result.current.selectedProject).toBe('p1');
    expect(onNoProjects).not.toHaveBeenCalled();
  });

  it('still calls onNoProjects (onboarding) for a genuinely empty, successful list', async () => {
    listProjects.mockResolvedValue([]);
    const onNoProjects = vi.fn();
    renderHook(() =>
      useProjectState({ onNoProjects, storage: noStorage, retryDelayMs: 0 }));

    await waitFor(() => expect(onNoProjects).toHaveBeenCalledTimes(1));
  });

  it('selects the first project on a successful non-empty load', async () => {
    listProjects.mockResolvedValue([{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }]);
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0 }));

    await waitFor(() => expect(result.current.selectedProject).toBe('a'));
  });
});

describe('useProjectState — recoverable failure state (v1.9.0 infinite spinner)', () => {
  it('exposes projectsLoadFailed=true after retries exhaust', async () => {
    listProjects.mockRejectedValue(new DOMException('aborted', 'AbortError'));
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0, maxRetries: 1 }));

    await waitFor(() => expect(result.current.projectsLoadFailed).toBe(true));
    expect(result.current.projectsLoaded).toBe(false);
  });

  it('retryLoadProjects clears the failure, reloads, and resolves the initial selection', async () => {
    listProjects.mockRejectedValue(new DOMException('aborted', 'AbortError'));
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0, maxRetries: 0 }));

    await waitFor(() => expect(result.current.projectsLoadFailed).toBe(true));

    listProjects.mockResolvedValue([{ id: 'p1', name: 'proj1' }]);
    await act(async () => { await result.current.retryLoadProjects(); });

    expect(result.current.projectsLoaded).toBe(true);
    expect(result.current.projectsLoadFailed).toBe(false);
    expect(result.current.selectedProject).toBe('p1');
  });

  it('a failed retry raises the failure flag again', async () => {
    listProjects.mockRejectedValue(new DOMException('aborted', 'AbortError'));
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0, maxRetries: 0 }));

    await waitFor(() => expect(result.current.projectsLoadFailed).toBe(true));

    await act(async () => { await result.current.retryLoadProjects(); });

    expect(result.current.projectsLoadFailed).toBe(true);
    expect(result.current.projectsLoaded).toBe(false);
  });
});

function makeMemoryStorage(initial = {}) {
  const store = { ...initial };
  return {
    store,
    getItem: (key) => (key in store ? store[key] : null),
    setItem: (key, value) => { store[key] = value; },
  };
}

describe('useProjectState — source-aware project selection', () => {
  it('defaults selectedSource to "local" when nothing is stored', async () => {
    listProjects.mockResolvedValue([{ id: 'a', name: 'A' }]);
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0 }));

    await waitFor(() => expect(result.current.selectedProject).toBe('a'));
    expect(result.current.selectedSource).toBe('local');
  });

  it('handleProjectChange(id, "shared") exposes and persists both keys', async () => {
    listProjects.mockResolvedValue([{ id: 'a', name: 'A' }]);
    const storage = makeMemoryStorage();
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage, retryDelayMs: 0 }));

    await waitFor(() => expect(result.current.selectedProject).toBe('a'));

    act(() => { result.current.handleProjectChange('shared-1', 'shared'); });

    expect(result.current.selectedProject).toBe('shared-1');
    expect(result.current.selectedSource).toBe('shared');
    expect(storage.store['quodeq_selected_project']).toBe('shared-1');
    expect(storage.store['quodeq_selected_source']).toBe('shared');
  });

  it('handleProjectChange(id) without a source resets source to "local"', async () => {
    listProjects.mockResolvedValue([{ id: 'a', name: 'A' }]);
    // Seed a stored project that matches the loaded list so the boot
    // resolution (resolveInitialProject) does not itself call
    // handleProjectChange and overwrite the seeded source first.
    const storage = makeMemoryStorage({ quodeq_selected_project: 'a', quodeq_selected_source: 'shared' });
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage, retryDelayMs: 0 }));

    await waitFor(() => expect(result.current.selectedProject).toBe('a'));
    // Restored from storage before any change is made.
    expect(result.current.selectedSource).toBe('shared');

    act(() => { result.current.handleProjectChange('local-1'); });

    expect(result.current.selectedProject).toBe('local-1');
    expect(result.current.selectedSource).toBe('local');
    expect(storage.store['quodeq_selected_source']).toBe('local');
  });

  it('falls back to "local" when the stored source value is invalid', async () => {
    listProjects.mockResolvedValue([{ id: 'a', name: 'A' }]);
    const storage = makeMemoryStorage({ quodeq_selected_project: 'a', quodeq_selected_source: 'bogus' });
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage, retryDelayMs: 0 }));

    await waitFor(() => expect(result.current.selectedProject).toBe('a'));
    expect(result.current.selectedSource).toBe('local');
  });

  it('keeps a restored shared selection on boot even though it is absent from the local projects list', async () => {
    // The boot-time resolution effect only ever loads the *local* project
    // list. A restored shared selection must not be validated against it
    // (and silently reverted to the first local project + source 'local') —
    // shared clones are resolved by Task 17's data hooks, not here.
    listProjects.mockResolvedValue([{ id: 'local-a', name: 'Local A' }]);
    const storage = makeMemoryStorage({ quodeq_selected_project: 'shared-xyz', quodeq_selected_source: 'shared' });
    const onNoProjects = vi.fn();
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects, storage, retryDelayMs: 0 }));

    await waitFor(() => expect(result.current.projectsLoaded).toBe(true));
    await new Promise((r) => setTimeout(r, 0)); // flush the resolution effect

    expect(result.current.selectedProject).toBe('shared-xyz');
    expect(result.current.selectedSource).toBe('shared');
    expect(onNoProjects).not.toHaveBeenCalled();
  });

  it('selectProjectAndRun pins source to "local" even when current source is "shared"', async () => {
    listProjects.mockResolvedValue([{ id: 'a', name: 'A' }]);
    const storage = makeMemoryStorage();
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage, retryDelayMs: 0 }));

    await waitFor(() => expect(result.current.selectedProject).toBe('a'));

    // Set source to 'shared'
    act(() => { result.current.handleProjectChange('shared-1', 'shared'); });
    expect(result.current.selectedSource).toBe('shared');

    // selectProjectAndRun on a different project must reset source to 'local'
    act(() => { result.current.selectProjectAndRun('local-2', 'run-123'); });

    expect(result.current.selectedProject).toBe('local-2');
    expect(result.current.selectedSource).toBe('local');
    expect(result.current.selectedRun).toBe('run-123');
    expect(storage.store['quodeq_selected_source']).toBe('local');
  });
});

describe('useProjectState — warm-up pending poll', () => {
  it('exposes the warmup snapshot from the projects envelope', async () => {
    listProjects.mockResolvedValue({
      projects: [{ id: 'a', name: 'A', summaryPending: false }],
      warmup: { active: true, projectsDone: 1, projectsTotal: 3, currentProjectName: 'A' },
    });
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0 }));

    await waitFor(() => expect(result.current.projectsLoaded).toBe(true));
    expect(result.current.warmup).toEqual({ active: true, projectsDone: 1, projectsTotal: 3, currentProjectName: 'A' });
  });

  it('polls while any summary is pending and stops when all settle', async () => {
    vi.useFakeTimers();
    try {
      listProjects
        .mockResolvedValueOnce({ projects: [{ id: 'a', name: 'A', summaryPending: true }], warmup: null })
        .mockResolvedValue({ projects: [{ id: 'a', name: 'A', summaryPending: false }], warmup: null });
      const { result } = renderHook(() =>
        useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0, summaryPollMs: 1000 }));

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(result.current.projects[0].summaryPending).toBe(true);

      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(listProjects).toHaveBeenCalledTimes(2);
      expect(result.current.projects[0].summaryPending).toBe(false);

      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      expect(listProjects).toHaveBeenCalledTimes(2); // settled -> no more polls
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not poll after the load has failed', async () => {
    vi.useFakeTimers();
    try {
      listProjects
        .mockResolvedValueOnce({ projects: [{ id: 'a', name: 'A', summaryPending: true }], warmup: null })
        .mockRejectedValue(new Error('down'));
      const { result } = renderHook(() =>
        useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0, maxRetries: 0, summaryPollMs: 1000 }));

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });   // poll fires, fails
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(result.current.projectsLoadFailed).toBe(true);
      const calls = listProjects.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
      expect(listProjects.mock.calls.length).toBe(calls);                    // failure stops the poll
    } finally {
      vi.useRealTimers();
    }
  });
});
