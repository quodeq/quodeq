import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRunEventStream } from './useRunEventStream.js';

class MockEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.closed = false;
    MockEventSource.last = this;
  }
  addEventListener(event, handler) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(handler);
  }
  close() {
    this.closed = true;
  }
  emit(event, data) {
    (this.listeners[event] || []).forEach((h) =>
      h({ data: JSON.stringify(data), lastEventId: data?.id })
    );
  }
}

describe('useRunEventStream', () => {
  let originalEventSource;
  beforeEach(() => {
    originalEventSource = globalThis.EventSource;
    globalThis.EventSource = MockEventSource;
    MockEventSource.last = null;
  });
  afterEach(() => {
    globalThis.EventSource = originalEventSource;
  });

  it('opens an EventSource against the run-events endpoint', () => {
    const { result } = renderHook(() => useRunEventStream('job-123'));
    expect(MockEventSource.last.url).toBe('/api/evaluations/job-123/events');
    expect(result.current.connected).toBe(true);
  });

  it('updates status state when status event arrives', () => {
    const { result } = renderHook(() => useRunEventStream('job-123'));
    act(() => {
      MockEventSource.last.emit('status', { state: 'running', phase: 'analyzing' });
    });
    expect(result.current.status).toEqual({ state: 'running', phase: 'analyzing' });
  });

  it('appends new findings as finding events arrive', () => {
    const { result } = renderHook(() => useRunEventStream('job-123'));
    act(() => {
      MockEventSource.last.emit('finding', { id: 1, practice_id: 'P1', verdict: 'violation' });
      MockEventSource.last.emit('finding', { id: 2, practice_id: 'P2', verdict: 'violation' });
    });
    expect(result.current.findings).toHaveLength(2);
    expect(result.current.findings[0].practice_id).toBe('P1');
  });

  it('tracks completed dimensions', () => {
    const { result } = renderHook(() => useRunEventStream('job-123'));
    act(() => {
      MockEventSource.last.emit('dimension-completed', { dimension: 'security', score: 90 });
    });
    expect(result.current.completedDimensions).toEqual({
      security: { dimension: 'security', score: 90 },
    });
  });

  it('sets done flag and closes the stream on done event', () => {
    const { result } = renderHook(() => useRunEventStream('job-123'));
    act(() => {
      MockEventSource.last.emit('done', { state: 'done' });
    });
    expect(result.current.done).toBe(true);
    expect(MockEventSource.last.closed).toBe(true);
  });

  it('returns null status when jobId is empty', () => {
    const { result } = renderHook(() => useRunEventStream(''));
    expect(result.current.status).toBeNull();
    expect(MockEventSource.last).toBeNull();
  });
});
