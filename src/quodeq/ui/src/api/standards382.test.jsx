/**
 * Finding #382 – importStandard() must apply a timeout to its fetch call.
 * The function has special 409-conflict handling that prevents it from using
 * request() directly (which throws on non-2xx before returning the body),
 * so the fix wraps the raw fetch with an AbortController + 30s timeout.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { importStandard } from './standards.js';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('#382 importStandard – 30s timeout', () => {
  it('calls fetch with an AbortSignal', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'std-1' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await importStandard({ id: 'std-1' });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.signal).toBeInstanceOf(AbortSignal);
  });

  it('aborts and rejects when the endpoint hangs past 30s', async () => {
    vi.useFakeTimers();
    let abortHandler;
    const fetchMock = vi.fn((_url, opts) =>
      new Promise((_resolve, reject) => {
        abortHandler = () => reject(new DOMException('Aborted', 'AbortError'));
        opts.signal.addEventListener('abort', abortHandler);
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const p = importStandard({ id: 'std-1' }).catch((e) => ({ error: e.message }));
    await vi.advanceTimersByTimeAsync(30001);
    const result = await p;

    expect(result).toMatchObject({ error: expect.any(String) });
    vi.useRealTimers();
  });

  it('still returns _conflict:true on 409 after timeout fix', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ error: 'Conflict', existing: true }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await importStandard({ id: 'std-1' });
    expect(result._conflict).toBe(true);
    expect(result.existing).toBe(true);
  });
});
