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
});
