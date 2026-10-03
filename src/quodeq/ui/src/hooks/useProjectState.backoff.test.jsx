import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

vi.mock('../api/index.js', () => ({ listProjects: vi.fn() }));
import { listProjects } from '../api/index.js';
import { useProjectState } from './useProjectState.js';
import { withQueryClient } from '../test-utils/withQueryClient.jsx';

const noStorage = { getItem: () => '', setItem: () => {} };

beforeEach(() => { listProjects.mockReset(); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe('useProjectState — retry backoff grows per attempt', () => {
  it('waits longer before the second retry than before the first (exponential, not flat)', async () => {
    vi.useFakeTimers();
    // Pin the shared backoffDelay's jitter to its floor (0.5) so the delays
    // below are exact: retryDelayMs=100 -> attempt0 waits 50ms, attempt1
    // waits 100ms. A flat (pre-fix) retryDelayMs would wait 100ms both times.
    vi.spyOn(Math, 'random').mockReturnValue(0);
    listProjects.mockRejectedValue(new Error('down'));

    renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 100, maxRetries: 2 }), { wrapper: withQueryClient() });

    // Initial attempt fires synchronously (microtask), rejects immediately.
    await vi.advanceTimersByTimeAsync(0);
    expect(listProjects).toHaveBeenCalledTimes(1);

    // First retry: must NOT have fired yet at 49ms, must have fired by 50ms.
    await vi.advanceTimersByTimeAsync(49);
    expect(listProjects).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(listProjects).toHaveBeenCalledTimes(2);

    // Second retry: waits ~100ms (double the first), not another flat 100.
    await vi.advanceTimersByTimeAsync(99);
    expect(listProjects).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(listProjects).toHaveBeenCalledTimes(3);
  });

  it('a retryDelayMs of 0 still resolves immediately (no jitter floor to overcome)', async () => {
    listProjects
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce([{ id: 'p1', name: 'proj1' }]);
    const { result } = renderHook(() =>
      useProjectState({ onNoProjects: vi.fn(), storage: noStorage, retryDelayMs: 0, maxRetries: 1 }), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.projects).toHaveLength(1));
  });
});
