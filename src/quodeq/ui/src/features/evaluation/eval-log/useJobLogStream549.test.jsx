/**
 * Finding #549 – useJobLogStream must close the EventSource and set
 * status='error' when no message arrives for 60 seconds (inactivity timer).
 * The timer resets on each message and on 'done'. It is cleared on unmount.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useJobLogStream } from './useJobLogStream.js';

class MockEventSource {
  static instances = [];
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.readyState = 0;
    this.closed = false;
    MockEventSource.instances.push(this);
  }
  addEventListener(name, fn) {
    (this.listeners[name] = this.listeners[name] || []).push(fn);
  }
  removeEventListener(name, fn) {
    this.listeners[name] = (this.listeners[name] || []).filter((f) => f !== fn);
  }
  set onmessage(fn) { this._onmessage = fn; }
  get onmessage() { return this._onmessage; }
  set onerror(fn) { this._onerror = fn; }
  get onerror() { return this._onerror; }
  emit(name, event) {
    if (name === 'message' && this._onmessage) this._onmessage(event);
    (this.listeners[name] || []).forEach((fn) => fn(event));
  }
  close() { this.closed = true; this.readyState = 2; }
}

function Probe({ jobId }) {
  const { logs, status } = useJobLogStream(jobId);
  return (
    <div>
      <div data-testid="status">{status}</div>
      <div data-testid="logs">{logs.join('|')}</div>
    </div>
  );
}

describe('#549 useJobLogStream inactivity timer', () => {
  let originalEventSource;
  beforeEach(() => {
    vi.useFakeTimers();
    originalEventSource = globalThis.EventSource;
    globalThis.EventSource = MockEventSource;
    MockEventSource.instances = [];
  });
  afterEach(() => {
    globalThis.EventSource = originalEventSource;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('closes the EventSource and sets status=error after 60s of inactivity', async () => {
    render(<Probe jobId="job-1" />);
    const es = MockEventSource.instances[0];
    expect(screen.getByTestId('status')).toHaveTextContent('streaming');

    // Advance 60 seconds with no message arriving.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });

    expect(es.closed).toBe(true);
    expect(screen.getByTestId('status')).toHaveTextContent('error');
  });

  it('resets the inactivity timer on each message so no timeout fires if active', async () => {
    render(<Probe jobId="job-2" />);
    const es = MockEventSource.instances[0];

    // Send messages every 30s — should not trigger the 60s timeout.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
      es.emit('message', { data: 'heartbeat' });
      await vi.advanceTimersByTimeAsync(30000);
      es.emit('message', { data: 'heartbeat 2' });
      await vi.advanceTimersByTimeAsync(30000);
    });

    expect(es.closed).toBe(false);
    expect(screen.getByTestId('status')).toHaveTextContent('streaming');
  });

  it('clears the inactivity timer on unmount to avoid state updates after unmount', async () => {
    const { unmount } = render(<Probe jobId="job-3" />);
    const es = MockEventSource.instances[0];
    unmount();

    // Advancing time after unmount must not throw or update state.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });

    // Stream is closed by unmount cleanup, not by the inactivity timer.
    expect(es.closed).toBe(true);
  });
});
