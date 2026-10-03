import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useHistoryRunLive } from './useHistoryRunLive.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { MockEventSource } from '../../../test-utils/MockEventSource.js';

describe('useHistoryRunLive', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', MockEventSource);
    MockEventSource.last = null;
  });

  it('returns empty defaults when no events have arrived', () => {
    const wrapper = withQueryClient();
    const { result } = renderHook(() => useHistoryRunLive('run-empty'), { wrapper });
    expect(result.current.liveDims).toEqual({});
    expect(result.current.plannedDimensions).toEqual([]);
    expect(result.current.hasScoredDimension).toBe(false);
  });

  it('opens an EventSource scoped to the runId', () => {
    const wrapper = withQueryClient();
    renderHook(() => useHistoryRunLive('run-xyz'), { wrapper });
    expect(MockEventSource.last.url).toBe('/api/evaluations/run-xyz/events');
  });

  it('surfaces dimension-completed events into liveDims', async () => {
    const wrapper = withQueryClient();
    const { result } = renderHook(() => useHistoryRunLive('run-1'), { wrapper });
    act(() => {
      MockEventSource.last.emit('dimension-completed', {
        dimension: 'security', score: 7.4,
      });
    });
    await waitFor(() => {
      expect(result.current.liveDims).toEqual({
        security: { dimension: 'security', score: 7.4 },
      });
    });
  });

  it('surfaces status.dimensions as plannedDimensions', async () => {
    const wrapper = withQueryClient();
    const { result } = renderHook(() => useHistoryRunLive('run-2'), { wrapper });
    act(() => {
      MockEventSource.last.emit('status', {
        state: 'running',
        dimensions: ['security', 'maintainability', 'performance'],
      });
    });
    await waitFor(() => {
      expect(result.current.plannedDimensions).toEqual([
        'security', 'maintainability', 'performance',
      ]);
    });
  });

  it('closes the EventSource on unmount', () => {
    const wrapper = withQueryClient();
    const { unmount } = renderHook(() => useHistoryRunLive('run-close'), { wrapper });
    const source = MockEventSource.last;
    unmount();
    expect(source.closed).toBe(true);
  });

  it('does not open EventSource when runId is empty', () => {
    const wrapper = withQueryClient();
    const { result } = renderHook(() => useHistoryRunLive(''), { wrapper });
    expect(MockEventSource.last).toBeNull();
    expect(result.current.hasScoredDimension).toBe(false);
  });

  it('hasScoredDimension flips on the first dimension-completed frame', async () => {
    // The server replays every completed dimension on connect, so the value
    // is right from the first tick without any per-row poll.
    const wrapper = withQueryClient();
    const { result } = renderHook(() => useHistoryRunLive('run-stream'), { wrapper });
    expect(result.current.hasScoredDimension).toBe(false);
    act(() => {
      MockEventSource.last.emit('dimension-completed', { dimension: 'security', score: 7 });
    });
    await waitFor(() => expect(result.current.hasScoredDimension).toBe(true));
  });
});
