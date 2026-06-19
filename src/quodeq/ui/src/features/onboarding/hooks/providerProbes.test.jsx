import { describe, it, expect, vi, afterEach } from 'vitest';
import { runDetection } from './providerProbes.js';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('providerProbes – timeout behaviour', () => {
  function successFetch() {
    return vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ clients: [] }),
    });
  }

  it('#261 detectCliProvider calls fetch with AbortSignal.timeout(5000)', async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(
      AbortSignal.abort() // only used to verify AbortSignal.timeout's return value is passed as opts.signal
    );
    const fetchMock = successFetch();
    vi.stubGlobal('fetch', fetchMock);

    await runDetection();

    expect(timeoutSpy).toHaveBeenCalledWith(5000);
    const clientCalls = fetchMock.mock.calls.filter(([url]) => url.includes('/ai-clients'));
    expect(clientCalls.length).toBeGreaterThanOrEqual(1);
    const [, opts] = clientCalls[0];
    expect(opts.signal).toBeInstanceOf(AbortSignal);
  });

  it('#261 detectCliProvider resolves to detected:false when fetch rejects (abort)', async () => {
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(AbortSignal.abort());
    const fetchMock = vi.fn().mockRejectedValue(
      new DOMException('The operation was aborted.', 'AbortError')
    );
    vi.stubGlobal('fetch', fetchMock);

    const results = await runDetection();
    const codex = results.find((r) => r.id === 'codex-cli');
    expect(codex).toBeDefined();
    expect(codex.detected).toBe(false);
  });

  it('#262 detectOllamaDaemon calls fetch with AbortSignal.timeout(5000)', async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(
      AbortSignal.abort()
    );
    const fetchMock = successFetch();
    vi.stubGlobal('fetch', fetchMock);

    await runDetection();

    expect(timeoutSpy).toHaveBeenCalledWith(5000);
    const ollamaCalls = fetchMock.mock.calls.filter(([url]) => url.includes('/ollama/'));
    expect(ollamaCalls.length).toBeGreaterThanOrEqual(1);
    const [, opts] = ollamaCalls[0];
    expect(opts.signal).toBeInstanceOf(AbortSignal);
  });

  it('#262 detectOllamaDaemon resolves to detected:false when fetch rejects (abort)', async () => {
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(AbortSignal.abort());
    const fetchMock = vi.fn().mockRejectedValue(
      new DOMException('The operation was aborted.', 'AbortError')
    );
    vi.stubGlobal('fetch', fetchMock);

    const results = await runDetection();
    const ollama = results.find((r) => r.id === 'ollama');
    expect(ollama).toBeDefined();
    expect(ollama.detected).toBe(false);
  });
});
