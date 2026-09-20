import { describe, it, expect, vi, afterEach } from 'vitest';
import { runDetection, PROBE_TIMEOUT_MS } from './providerProbes.js';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('providerProbes – timeout behaviour', () => {
  it.each([true, false])('detects Copilot only when installed=%s', async (installed) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ clients: [{ id: 'copilot', type: 'cli', installed }] }),
    }));
    const results = await runDetection();
    expect(results.find((r) => r.id === 'copilot')).toMatchObject({ detected: installed });
  });

  function successFetch() {
    return vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ clients: [] }),
    });
  }

  it('#261 detectCliProvider calls fetch with AbortSignal.timeout(PROBE_TIMEOUT_MS)', async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(
      AbortSignal.abort() // only used to verify AbortSignal.timeout's return value is passed as opts.signal
    );
    const fetchMock = successFetch();
    vi.stubGlobal('fetch', fetchMock);

    await runDetection();

    expect(timeoutSpy).toHaveBeenCalledWith(PROBE_TIMEOUT_MS);
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

  it('#262 detectOllamaDaemon calls fetch with AbortSignal.timeout(PROBE_TIMEOUT_MS)', async () => {
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(
      AbortSignal.abort()
    );
    const fetchMock = successFetch();
    vi.stubGlobal('fetch', fetchMock);

    await runDetection();

    expect(timeoutSpy).toHaveBeenCalledWith(PROBE_TIMEOUT_MS);
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

describe('providerProbes – detectStoredCloudKey', () => {
  function keyStatusFetch(configured) {
    return vi.fn((url) => {
      if (url.includes('/provider/key-status')) {
        return Promise.resolve({ ok: true, json: async () => ({ configured }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ clients: [] }) });
    });
  }

  it('calls GET /api/provider/key-status?provider=<id> and returns detected:true when configured', async () => {
    const fetchMock = keyStatusFetch(true);
    vi.stubGlobal('fetch', fetchMock);

    const results = await runDetection();
    const openai = results.find((r) => r.id === 'openai');
    expect(openai).toBeDefined();
    expect(openai.detected).toBe(true);

    const keyStatusCalls = fetchMock.mock.calls.filter(([url]) => url.includes('/provider/key-status'));
    expect(keyStatusCalls.some(([url]) => url.includes('provider=openai'))).toBe(true);
    expect(keyStatusCalls.some(([url]) => url.includes('provider=anthropic'))).toBe(true);
  });

  it('returns detected:false when the status endpoint reports not configured', async () => {
    vi.stubGlobal('fetch', keyStatusFetch(false));

    const results = await runDetection();
    const anthropic = results.find((r) => r.id === 'anthropic');
    expect(anthropic.detected).toBe(false);
  });

  it('resolves to detected:false when the status fetch rejects', async () => {
    const fetchMock = vi.fn((url) => {
      if (url.includes('/provider/key-status')) return Promise.reject(new Error('network error'));
      return Promise.resolve({ ok: true, json: async () => ({ clients: [] }) });
    });
    vi.stubGlobal('fetch', fetchMock);

    const results = await runDetection();
    const openai = results.find((r) => r.id === 'openai');
    expect(openai.detected).toBe(false);
  });

  it('never reads localStorage to determine whether a key is configured', async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem');
    vi.stubGlobal('fetch', keyStatusFetch(true));

    await runDetection();

    expect(getItemSpy).not.toHaveBeenCalled();
  });
});
