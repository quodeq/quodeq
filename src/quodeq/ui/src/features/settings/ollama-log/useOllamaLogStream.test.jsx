import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useOllamaLogStream } from './useOllamaLogStream.js';

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
  close() { this.closed = true; this.readyState = 2; }
}

function Probe({ active }) {
  const { logs, firstSeq, status } = useOllamaLogStream(active);
  return (
    <div>
      <div data-testid="status">{status}</div>
      <div data-testid="logs">{logs.join('|')}</div>
      <div data-testid="first-seq">{String(firstSeq)}</div>
    </div>
  );
}

describe('useOllamaLogStream', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', MockEventSource);
    MockEventSource.instances = [];
  });

  it('does not open EventSource when active=false', () => {
    render(<Probe active={false} />);
    expect(MockEventSource.instances).toHaveLength(0);
    expect(screen.getByTestId('status')).toHaveTextContent('idle');
  });

  it('opens EventSource at /api/ollama/logs/stream when active=true', () => {
    render(<Probe active={true} />);
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/ollama/logs/stream');
    expect(screen.getByTestId('status')).toHaveTextContent('streaming');
  });

  it('appends each message event to logs[]', () => {
    render(<Probe active={true} />);
    const es = MockEventSource.instances[0];
    act(() => { es.emit('message', { data: 'line one' }); });
    act(() => { es.emit('message', { data: 'line two' }); });
    expect(screen.getByTestId('logs')).toHaveTextContent('line one|line two');
  });

  it('caps the buffer at 5000 lines', () => {
    render(<Probe active={true} />);
    const es = MockEventSource.instances[0];
    act(() => {
      for (let i = 0; i < 5050; i++) es.emit('message', { data: `line-${i}` });
    });
    const text = screen.getByTestId('logs').textContent;
    const lines = text.split('|');
    expect(lines.length).toBe(5000);
    expect(lines[0]).toBe('line-50');
    expect(lines[lines.length - 1]).toBe('line-5049');
  });

  it('closes EventSource on active=false toggle', () => {
    const { rerender } = render(<Probe active={true} />);
    const es = MockEventSource.instances[0];
    rerender(<Probe active={false} />);
    expect(es.closed).toBe(true);
    expect(screen.getByTestId('status')).toHaveTextContent('idle');
  });

  it('closes EventSource on unmount', () => {
    const { unmount } = render(<Probe active={true} />);
    const es = MockEventSource.instances[0];
    unmount();
    expect(es.closed).toBe(true);
  });

  it('toggling the panel off moves firstSeq past the streamed lines', () => {
    const { rerender } = render(<Probe active />);
    const es = MockEventSource.instances[MockEventSource.instances.length - 1];
    act(() => { es.emit('message', { data: 'x' }); es.emit('message', { data: 'y' }); });
    expect(screen.getByTestId('first-seq')).toHaveTextContent('0');
    rerender(<Probe active={false} />);
    expect(screen.getByTestId('logs').textContent).toBe('');
    expect(screen.getByTestId('first-seq')).toHaveTextContent('2');
  });
});
