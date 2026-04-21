import { render, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LiveTerminal from './LiveTerminal.jsx';

class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    FakeEventSource.instances.push(this);
  }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  close() { this.closed = true; }
  _emit(name, data) { this.listeners[name] && this.listeners[name]({ data }); }
}
FakeEventSource.instances = [];

describe('LiveTerminal', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    global.EventSource = FakeEventSource;
  });

  it('mounts and opens an EventSource for the given job', () => {
    render(<LiveTerminal jobId="job-xyz" />);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe('/api/jobs/job-xyz/logs/stream');
  });

  it('closes the EventSource on unmount', () => {
    const { unmount } = render(<LiveTerminal jobId="job-xyz" />);
    const es = FakeEventSource.instances[0];
    unmount();
    expect(es.closed).toBe(true);
  });

  it('closes the EventSource when a done event fires', () => {
    render(<LiveTerminal jobId="job-xyz" />);
    const es = FakeEventSource.instances[0];
    act(() => { es._emit('done', ''); });
    expect(es.closed).toBe(true);
  });
});
