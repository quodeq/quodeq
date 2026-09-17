import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { notifyStandardsChanged, STANDARDS_CHANGED_REASON } from '../../../constants.js';

vi.mock('../../../utils/visibleStandards.js', () => ({
  readVisibleStandardIds: vi.fn(),
}));

const { readVisibleStandardIds } = await import('../../../utils/visibleStandards.js');
const { usePluginDimensions, invalidateDimensionCache, createDimensionCache } =
  await import('./usePluginDimensions.js');

function makeWrapper(fakeApi) {
  return function Wrapper({ children }) {
    return <ApiProvider value={fakeApi}>{children}</ApiProvider>;
  };
}

describe('usePluginDimensions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    invalidateDimensionCache();
  });

  it('matches a visible-standards id case-insensitively', async () => {
    // The server normalizes stored ids to lowercase, but a custom/imported
    // standard's own id isn't charset-constrained (e.g. "OWASP-Top10"). The
    // stored selection carries the lowercase form; the dimension itself
    // keeps its original casing. Both sides must be compared lowercase or
    // the dimension wrongly disappears from the scan picker.
    readVisibleStandardIds.mockReturnValue(['owasp-top10']);
    const fakeApi = {
      listPlugins: vi.fn().mockResolvedValue([
        { dimensions: [{ id: 'OWASP-Top10', label: 'OWASP Top 10' }] },
      ]),
      listStandards: vi.fn().mockResolvedValue([]),
    };
    const { result } = renderHook(() => usePluginDimensions(), {
      wrapper: makeWrapper(fakeApi),
    });
    await waitFor(() => expect(result.current.allDimensions).toHaveLength(1));
    expect(result.current.allDimensions[0].id).toBe('OWASP-Top10');
  });

  it('filters out a dimension whose id is not in the visible set', async () => {
    readVisibleStandardIds.mockReturnValue(['security']);
    const fakeApi = {
      listPlugins: vi.fn().mockResolvedValue([
        { dimensions: [{ id: 'OWASP-Top10', label: 'OWASP Top 10' }] },
      ]),
      listStandards: vi.fn().mockResolvedValue([]),
    };
    const { result } = renderHook(() => usePluginDimensions(), {
      wrapper: makeWrapper(fakeApi),
    });
    await waitFor(() => expect(fakeApi.listPlugins).toHaveBeenCalled());
    expect(result.current.allDimensions).toHaveLength(0);
  });

  it('refilters an already-mounted picker from cache when visibility changes, without refetching', async () => {
    // Starring a standard on the Standards page (or switching project, which
    // re-hydrates the visible set) must reach a picker that is already on
    // screen. Before, the list was filtered once per mount and stayed stale.
    readVisibleStandardIds.mockReturnValue(['security']);
    const cache = createDimensionCache();
    const fakeApi = {
      listPlugins: vi.fn().mockResolvedValue([{ dimensions: [{ id: 'security', label: 'Security' }] }]),
      listStandards: vi.fn().mockResolvedValue([{ id: 'accessibility', name: 'Accessibility', type: 'custom' }]),
    };
    const { result } = renderHook(() => usePluginDimensions(cache), { wrapper: makeWrapper(fakeApi) });
    await waitFor(() => expect(result.current.allDimensions).toHaveLength(1));

    readVisibleStandardIds.mockReturnValue(['security', 'accessibility']);
    act(() => notifyStandardsChanged(STANDARDS_CHANGED_REASON.VISIBILITY));

    expect(result.current.allDimensions.map((d) => d.id)).toEqual(['security', 'accessibility']);
    expect(fakeApi.listStandards).toHaveBeenCalledTimes(1);
  });

  it('refetches when the standards list changes so a new custom standard appears without a reload', async () => {
    readVisibleStandardIds.mockReturnValue(['security', 'accessibility']);
    const cache = createDimensionCache();
    const fakeApi = {
      listPlugins: vi.fn().mockResolvedValue([{ dimensions: [{ id: 'security', label: 'Security' }] }]),
      listStandards: vi.fn().mockResolvedValue([]),
    };
    const { result } = renderHook(() => usePluginDimensions(cache), { wrapper: makeWrapper(fakeApi) });
    await waitFor(() => expect(result.current.allDimensions).toHaveLength(1));

    fakeApi.listStandards.mockResolvedValue([{ id: 'accessibility', name: 'Accessibility', type: 'custom' }]);
    act(() => notifyStandardsChanged(STANDARDS_CHANGED_REASON.LIST));

    await waitFor(() => expect(result.current.allDimensions).toHaveLength(2));
    expect(fakeApi.listStandards).toHaveBeenCalledTimes(2);
    expect(result.current.allDimensions[1].standardType).toBe('custom');
  });

  it('refetches on a visibility change that names a standard the cache has never seen', async () => {
    // A JSON dropped into ~/.quodeq/evaluators after the picker loaded, then
    // starred on the Standards page: the star only says "visibility", but
    // refiltering the stale cache could never show it.
    readVisibleStandardIds.mockReturnValue(['security']);
    const cache = createDimensionCache();
    const fakeApi = {
      listPlugins: vi.fn().mockResolvedValue([{ dimensions: [{ id: 'security', label: 'Security' }] }]),
      listStandards: vi.fn().mockResolvedValue([]),
    };
    const { result } = renderHook(() => usePluginDimensions(cache), { wrapper: makeWrapper(fakeApi) });
    await waitFor(() => expect(result.current.allDimensions).toHaveLength(1));

    fakeApi.listStandards.mockResolvedValue([{ id: 'accessibility', name: 'Accessibility', type: 'custom' }]);
    readVisibleStandardIds.mockReturnValue(['security', 'accessibility']);
    act(() => notifyStandardsChanged(STANDARDS_CHANGED_REASON.VISIBILITY));

    await waitFor(() => expect(result.current.allDimensions).toHaveLength(2));
    expect(fakeApi.listStandards).toHaveBeenCalledTimes(2);
  });

  it('a picker mounting onto a cache that predates a starred standard refetches instead of reusing it', async () => {
    readVisibleStandardIds.mockReturnValue(['security']);
    const cache = createDimensionCache();
    const fakeApi = {
      listPlugins: vi.fn().mockResolvedValue([{ dimensions: [{ id: 'security', label: 'Security' }] }]),
      listStandards: vi.fn().mockResolvedValue([]),
    };
    const first = renderHook(() => usePluginDimensions(cache), { wrapper: makeWrapper(fakeApi) });
    await waitFor(() => expect(first.result.current.allDimensions).toHaveLength(1));
    first.unmount();

    fakeApi.listStandards.mockResolvedValue([{ id: 'accessibility', name: 'Accessibility', type: 'custom' }]);
    readVisibleStandardIds.mockReturnValue(['security', 'accessibility']);
    const second = renderHook(() => usePluginDimensions(cache), { wrapper: makeWrapper(fakeApi) });

    await waitFor(() => expect(second.result.current.allDimensions).toHaveLength(2));
    expect(fakeApi.listStandards).toHaveBeenCalledTimes(2);
  });

  it('two mounted pickers share one refetch per list change', async () => {
    readVisibleStandardIds.mockReturnValue(['security']);
    const cache = createDimensionCache();
    const fakeApi = {
      listPlugins: vi.fn().mockResolvedValue([{ dimensions: [{ id: 'security', label: 'Security' }] }]),
      listStandards: vi.fn().mockResolvedValue([]),
    };
    const wrapper = makeWrapper(fakeApi);
    const first = renderHook(() => usePluginDimensions(cache), { wrapper });
    const second = renderHook(() => usePluginDimensions(cache), { wrapper });
    await waitFor(() => expect(first.result.current.allDimensions).toHaveLength(1));
    await waitFor(() => expect(second.result.current.allDimensions).toHaveLength(1));
    expect(fakeApi.listStandards).toHaveBeenCalledTimes(1);

    act(() => notifyStandardsChanged(STANDARDS_CHANGED_REASON.LIST));

    await waitFor(() => expect(fakeApi.listStandards).toHaveBeenCalledTimes(2));
    await act(async () => { await cache.load(fakeApi.listPlugins, fakeApi.listStandards); });
    expect(fakeApi.listStandards).toHaveBeenCalledTimes(2);
  });

  it('sets dimLoadError when the load fails (cache.load now rejects instead of swallowing to [])', async () => {
    readVisibleStandardIds.mockReturnValue(['security']);
    const cache = createDimensionCache();
    const fakeApi = {
      // listPlugins/listStandards degrade individually to `[]`; force the
      // failure inside dedup so cache.load's own promise rejects.
      listPlugins: vi.fn().mockResolvedValue([{ dimensions: null }]),
      listStandards: vi.fn().mockResolvedValue([]),
    };
    const { result } = renderHook(() => usePluginDimensions(cache), {
      wrapper: makeWrapper(fakeApi),
    });
    await waitFor(() => expect(result.current.dimLoadError).toBeTruthy());
    expect(result.current.allDimensions).toEqual([]);
  });

  it('accepts an injected cache instance so tests never touch the module singleton', async () => {
    readVisibleStandardIds.mockReturnValue(['security']);
    const cache = createDimensionCache();
    const fakeApi = {
      listPlugins: vi.fn().mockResolvedValue([
        { dimensions: [{ id: 'security', label: 'Security' }] },
      ]),
      listStandards: vi.fn().mockResolvedValue([]),
    };
    const { result } = renderHook(() => usePluginDimensions(cache), {
      wrapper: makeWrapper(fakeApi),
    });
    await waitFor(() => expect(result.current.allDimensions).toHaveLength(1));
    // The isolated instance holds the load; the shared singleton stays cold
    // (beforeEach invalidated it and nothing above touched it).
    expect(cache.get()).toHaveLength(1);
  });
});

describe('createDimensionCache', () => {
  const plugins = [{ dimensions: [{ id: 'security', label: 'Security' }] }];

  it('single-flights concurrent loads and reuses the resolved list', async () => {
    const cache = createDimensionCache();
    const listPlugins = vi.fn().mockResolvedValue(plugins);
    const listStandards = vi.fn().mockResolvedValue([]);
    const [a, b] = await Promise.all([
      cache.load(listPlugins, listStandards),
      cache.load(listPlugins, listStandards),
    ]);
    expect(a).toBe(b);
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(listStandards).toHaveBeenCalledTimes(1);
    // A later load after resolution still reuses the cached promise.
    await cache.load(listPlugins, listStandards);
    expect(listPlugins).toHaveBeenCalledTimes(1);
    expect(cache.get()).toHaveLength(1);
  });

  it('invalidate() drops the cached list and lets the next load refetch', async () => {
    const cache = createDimensionCache();
    const listPlugins = vi.fn().mockResolvedValue(plugins);
    const listStandards = vi.fn().mockResolvedValue([]);
    await cache.load(listPlugins, listStandards);
    cache.invalidate();
    expect(cache.get()).toBeNull();
    await cache.load(listPlugins, listStandards);
    expect(listPlugins).toHaveBeenCalledTimes(2);
    expect(cache.get()).toHaveLength(1);
  });

  it('rejects instead of resolving to [] on failure, and clears the cached promise for retry', async () => {
    const cache = createDimensionCache();
    const listPlugins = vi.fn().mockResolvedValue([{ dimensions: null }]); // breaks dedup
    const listStandards = vi.fn().mockResolvedValue([]);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await expect(cache.load(listPlugins, listStandards)).rejects.toBeTruthy();
    expect(cache.get()).toBeNull();

    // A retry after the rejection issues fresh calls (cachePromise was
    // cleared) instead of replaying the same rejected promise forever.
    listPlugins.mockResolvedValueOnce(plugins);
    await cache.load(listPlugins, listStandards);
    expect(listPlugins).toHaveBeenCalledTimes(2);
    expect(cache.get()).toHaveLength(1);

    warnSpy.mockRestore();
  });

  it('two instances do not share state', async () => {
    const a = createDimensionCache();
    const b = createDimensionCache();
    await a.load(vi.fn().mockResolvedValue(plugins), vi.fn().mockResolvedValue([]));
    expect(a.get()).toHaveLength(1);
    expect(b.get()).toBeNull();
  });
});
