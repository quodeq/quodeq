import { vi, it, expect, afterEach } from 'vitest';
import { request } from './request.js';
afterEach(() => vi.restoreAllMocks());

it('aborts when the caller signal aborts (react-query cancellation preserved)', async () => {
  const fetchMock = vi.fn((_u, opts) => new Promise((_, reject) => {
    opts.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  }));
  vi.stubGlobal('fetch', fetchMock);
  const ctrl = new AbortController();
  const p = request('/x', { signal: ctrl.signal });
  ctrl.abort();
  await expect(p).rejects.toThrow();
  expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
});

it('aborts on the internal timeout when no caller signal is given', async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn((_u, opts) => new Promise((resolve, reject) => {
    opts.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  }));
  vi.stubGlobal('fetch', fetchMock);
  const p = request('/x');
  // Suppress unhandled-rejection noise while fake timers advance
  p.catch(() => {});
  await vi.advanceTimersByTimeAsync(30000);
  await expect(p).rejects.toThrow();
  vi.useRealTimers();
});
