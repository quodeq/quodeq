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

it('attaches the HTTP status to thrown errors so callers can branch on it', async () => {
  // The cancel flow needs to distinguish "409 job no longer cancellable"
  // (drop the job) from a transient 500/timeout (keep it); a bare Error
  // forced callers to treat every failure as fatal.
  const fetchMock = vi.fn(async () => ({
    ok: false,
    status: 409,
    json: async () => ({ error: 'not cancellable' }),
  }));
  vi.stubGlobal('fetch', fetchMock);
  await request('/x').then(
    () => { throw new Error('expected rejection'); },
    (err) => {
      expect(err.message).toBe('not cancellable');
      expect(err.status).toBe(409);
    },
  );
});
