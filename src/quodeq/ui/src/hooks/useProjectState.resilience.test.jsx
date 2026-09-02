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

  it('auto-retries in the background while failed, staying on the failed state', async () => {
    vi.useFakeTimers();
    try {
      listProjects.mockRejectedValue(new Error('down'));
      const { result } = renderHook(() =>
        useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0, maxRetries: 0, autoRetryMs: 1000 }));

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(result.current.projectsLoadFailed).toBe(true);
      const calls = listProjects.mock.calls.length;

      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(listProjects.mock.calls.length).toBe(calls + 1);
      // The silent attempt failed again: no flicker back to the loading state.
      expect(result.current.projectsLoadFailed).toBe(true);
      expect(result.current.projectsLoaded).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('recovers on its own when a background retry succeeds', async () => {
    vi.useFakeTimers();
    try {
      listProjects.mockRejectedValue(new Error('down'));
      const { result } = renderHook(() =>
        useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0, maxRetries: 0, autoRetryMs: 1000 }));

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(result.current.projectsLoadFailed).toBe(true);

      listProjects.mockResolvedValue({ projects: [{ id: 'p1', name: 'proj1' }], warmup: null });
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

      expect(result.current.projectsLoaded).toBe(true);
      expect(result.current.projectsLoadFailed).toBe(false);
      expect(result.current.selectedProject).toBe('p1');
    } finally {
      vi.useRealTimers();
    }
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
