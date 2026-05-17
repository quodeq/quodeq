import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { MockEventSource } from '../../../test-utils/MockEventSource.js';
import { useGradeStream } from './useGradeStream';

describe('useGradeStream', () => {
  let originalEventSource;

  beforeEach(() => {
    originalEventSource = global.EventSource;
    MockEventSource.last = null;
    global.EventSource = MockEventSource;
  });

  afterEach(() => {
    global.EventSource = originalEventSource;
  });

  it('returns idle when runId is null', () => {
    const { result } = renderHook(() => useGradeStream({ project: 'p', runId: null }));
    expect(result.current.payload).toBeNull();
    expect(result.current.status).toBe('idle');
    expect(MockEventSource.last).toBeNull();
  });

  it('subscribes on mount and parses scores.updated payload', () => {
    const { result } = renderHook(() => useGradeStream({ project: 'p', runId: 'r1' }));
    expect(MockEventSource.last).not.toBeNull();
    expect(MockEventSource.last.url).toBe('/api/evaluations/r1/events');
    expect(result.current.status).toBe('streaming');

    const payload = {
      dimensions: [{ dimension: 'Security', overallScore: '7.4/10', overallGrade: 'B' }],
      summary: { overallGrade: 'B', numericAverage: 7.4 },
    };
    act(() => { MockEventSource.last.emit('scores.updated', payload); });

    expect(result.current.payload).toEqual(payload);
    expect(result.current.isStale).toBe(false);
  });

  it('ignores non-scores events', () => {
    const { result } = renderHook(() => useGradeStream({ project: 'p', runId: 'r1' }));

    act(() => { MockEventSource.last.emit('finding', { id: 1, file: 'a.py' }); });
    act(() => { MockEventSource.last.emit('status', { state: 'running' }); });

    expect(result.current.payload).toBeNull();
  });

  it('closes the connection on unmount', () => {
    const { unmount } = renderHook(() => useGradeStream({ project: 'p', runId: 'r1' }));
    const es = MockEventSource.last;
    expect(es.closed).not.toBe(true);
    unmount();
    expect(es.closed).toBe(true);
  });

  it('sets isStale on error', () => {
    const { result } = renderHook(() => useGradeStream({ project: 'p', runId: 'r1' }));
    const es = MockEventSource.last;

    act(() => {
      es.readyState = 2;
      if (es.onerror) es.onerror({ type: 'error' });
    });

    expect(result.current.isStale).toBe(true);
    expect(result.current.status).toBe('error');
  });

  it('survives malformed payload (keeps prior payload, no crash)', () => {
    const { result } = renderHook(() => useGradeStream({ project: 'p', runId: 'r1' }));

    const goodPayload = { dimensions: [], summary: {} };
    act(() => { MockEventSource.last.emit('scores.updated', goodPayload); });
    expect(result.current.payload).toEqual(goodPayload);

    // Now emit a raw string that is already JSON-stringified by MockEventSource,
    // making the inner JSON.parse see a bare string — not an object.
    // We fire the event handler directly with non-JSON data to simulate malformed frame.
    act(() => {
      const listeners = MockEventSource.last.listeners['scores.updated'] || [];
      listeners.forEach((fn) => fn({ data: '{invalid-json}' }));
    });

    expect(result.current.payload).toEqual(goodPayload); // prior preserved
  });
});
