import { render, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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

function mockFetch(status, extra = {}) {
  global.fetch = vi.fn(() => Promise.resolve({
    status,
    ok: status >= 200 && status < 300,
    ...extra,
  }));
}

describe('LiveTerminal', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    global.EventSource = FakeEventSource;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('probes the plain logs endpoint before opening SSE', async () => {
    mockFetch(200);
    render(<LiveTerminal jobId="job-xyz" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    // The first request should be to the plain endpoint (probe), then SSE.
    expect(global.fetch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/jobs\/job-xyz\/logs\?since=0$/));
    expect(FakeEventSource.instances[0].url).toBe('/api/jobs/job-xyz/logs/stream');
  });

  it('renders placeholder and does NOT open SSE on 404 probe', async () => {
    mockFetch(404);
    const { container } = render(<LiveTerminal jobId="job-missing" />);
    // Wait for the fetch promise chain to settle.
    await waitFor(() => expect(container.textContent).toMatch(/Terminal \(1 lines?\)/));
    // No SSE connection opened — avoids the infinite-reconnect bug.
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('renders placeholder on 410 (run artifacts removed)', async () => {
    mockFetch(410);
    const { container } = render(<LiveTerminal jobId="job-gone" />);
    await waitFor(() => expect(container.textContent).toMatch(/Terminal \(1 lines?\)/));
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('renders placeholder when probe fetch rejects (network error)', async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error('network down')));
    const { container } = render(<LiveTerminal jobId="job-net" />);
    await waitFor(() => expect(container.textContent).toMatch(/Terminal \(1 lines?\)/));
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('closes the EventSource on unmount', async () => {
    mockFetch(200);
    const { unmount } = render(<LiveTerminal jobId="job-unmount" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];
    unmount();
    expect(es.closed).toBe(true);
  });

  it('closes the EventSource when a done event fires', async () => {
    mockFetch(200);
    render(<LiveTerminal jobId="job-done" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];
    act(() => { es._emit('done', ''); });
    expect(es.closed).toBe(true);
  });

  it('skips SSE entirely if unmounted before probe resolves', async () => {
    let resolveProbe;
    global.fetch = vi.fn(() => new Promise((resolve) => { resolveProbe = resolve; }));
    const { unmount } = render(<LiveTerminal jobId="job-early-unmount" />);
    // Unmount BEFORE the probe resolves.
    unmount();
    // Now resolve the probe — should be ignored (cancelled guard).
    act(() => { resolveProbe({ status: 200, ok: true }); });
    // Wait a tick for any would-be SSE creation to happen.
    await new Promise((r) => setTimeout(r, 10));
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
