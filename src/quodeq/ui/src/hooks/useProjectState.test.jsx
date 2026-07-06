import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

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
