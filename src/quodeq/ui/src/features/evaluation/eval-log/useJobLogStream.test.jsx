import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useJobLogStream } from './useJobLogStream.js';

// The hook coalesces SSE bursts via requestAnimationFrame + a 50ms timer
// fallback. Tests need to drain that queue between an emit and an assertion.
function flushBatched() {
  act(() => {
    vi.runAllTimers();
  });
}

// --- Mock EventSource ---
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
  close() { this.closed = true; }
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

describe('useJobLogStream', () => {
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
  });

  it('opens EventSource at the right URL for given jobId', () => {
    render(<Probe jobId="abc123" />);
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/jobs/abc123/logs/stream');
    expect(screen.getByTestId('status')).toHaveTextContent('streaming');
  });

  it('appends each message event to logs[]', () => {
    render(<Probe jobId="j1" />);
    const es = MockEventSource.instances[0];
    act(() => { es.emit('message', { data: 'first line' }); });
    act(() => { es.emit('message', { data: 'second line' }); });
    flushBatched();
    expect(screen.getByTestId('logs')).toHaveTextContent('first line|second line');
  });

  it('switches to done status and closes the stream on done event', () => {
    render(<Probe jobId="j1" />);
    const es = MockEventSource.instances[0];
    act(() => { es.emit('done', {}); });
    expect(screen.getByTestId('status')).toHaveTextContent('done');
    expect(es.closed).toBe(true);
  });

  it('caps the buffer at 5000 lines, dropping from the front', () => {
    render(<Probe jobId="j1" />);
    const es = MockEventSource.instances[0];
    act(() => {
      for (let i = 0; i < 5050; i++) es.emit('message', { data: `line-${i}` });
    });
    flushBatched();
    const text = screen.getByTestId('logs').textContent;
    const lines = text.split('|');
    expect(lines.length).toBe(5000);
    expect(lines[0]).toBe('line-50');
    expect(lines[lines.length - 1]).toBe('line-5049');
  });

  it('closes the EventSource on unmount', () => {
    const { unmount } = render(<Probe jobId="j1" />);
    const es = MockEventSource.instances[0];
    unmount();
    expect(es.closed).toBe(true);
  });

  it('switching jobId clears logs and opens a new EventSource', () => {
    const { rerender } = render(<Probe jobId="j1" />);
    const first = MockEventSource.instances[0];
    act(() => { first.emit('message', { data: 'old' }); });
    rerender(<Probe jobId="j2" />);
    expect(first.closed).toBe(true);
    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1].url).toBe('/api/jobs/j2/logs/stream');
    expect(screen.getByTestId('logs').textContent).toBe('');
  });

  it('null jobId leaves status idle and opens no connection', () => {
    render(<Probe jobId={null} />);
    expect(MockEventSource.instances).toHaveLength(0);
    expect(screen.getByTestId('status')).toHaveTextContent('idle');
  });
});
