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

it('sends a FormData body with no Content-Type header, so the browser sets the multipart boundary', async () => {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ ok: true }),
  }));
  vi.stubGlobal('fetch', fetchMock);
  const form = new FormData();
  form.append('file', new Blob(['x']), 'x.zip');
  await request('/x', { method: 'POST', body: form });
  const [, opts] = fetchMock.mock.calls[0];
  expect(opts.body).toBe(form);
  expect(opts.headers['Content-Type']).toBeUndefined();
});

it('still sends the JSON Content-Type for a plain (non-FormData) body', async () => {
  const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
  vi.stubGlobal('fetch', fetchMock);
  await request('/x', { method: 'POST', body: JSON.stringify({ a: 1 }) });
  const [, opts] = fetchMock.mock.calls[0];
  expect(opts.headers['Content-Type']).toBe('application/json');
});

it('timeout: null disables the internal abort, for uploads with no time cap', async () => {
  vi.useFakeTimers();
  const fetchMock = vi.fn((_u, opts) => new Promise((resolve, reject) => {
    opts.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    // Never resolves/rejects on its own within the test window.
  }));
  vi.stubGlobal('fetch', fetchMock);
  const p = request('/x', { timeout: null });
  p.catch(() => {});
  await vi.advanceTimersByTimeAsync(120000);
  expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(false);
  vi.useRealTimers();
});
