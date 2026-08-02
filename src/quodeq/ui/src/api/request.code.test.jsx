// request() built the error from `payload.error` and threw away
// `payload.code`. That single omission is why no screen could ever turn a
// backend failure into translated copy: the sentence was the only thing that
// crossed the boundary, and it is written in Python source. Pin the
// propagation so it cannot regress silently.
//
// Lives in vitest rather than node:test because request.js reads
// import.meta.env, which only exists under Vite.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { request } from './request.js';

function stubFetch(status, payload) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: status < 400,
    status,
    json: async () => payload,
  })));
}

afterEach(() => vi.unstubAllGlobals());

describe('request() error envelope', () => {
  it('attaches the stable code alongside status and message', async () => {
    stubFetch(404, { error: 'Run not found', code: 'NOT_FOUND' });
    await expect(request('/x')).rejects.toMatchObject({
      code: 'NOT_FOUND',
      status: 404,
      message: 'Run not found',
    });
  });

  it('yields null for a code-less envelope rather than leaving it undefined', async () => {
    stubFetch(500, { error: 'boom' });
    await expect(request('/x')).rejects.toMatchObject({ code: null, status: 500 });
  });

  it('still synthesises a message when the envelope carries none', async () => {
    stubFetch(503, {});
    await expect(request('/x')).rejects.toThrow('Request failed: 503');
  });

  it('leaves successful responses untouched', async () => {
    stubFetch(200, { ok: true, value: 3 });
    await expect(request('/x')).resolves.toEqual({ ok: true, value: 3 });
  });
});
