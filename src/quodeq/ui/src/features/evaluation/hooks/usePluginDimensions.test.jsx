import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { ApiProvider } from '../../../api/ApiContext.jsx';

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

  it('two instances do not share state', async () => {
    const a = createDimensionCache();
    const b = createDimensionCache();
    await a.load(vi.fn().mockResolvedValue(plugins), vi.fn().mockResolvedValue([]));
    expect(a.get()).toHaveLength(1);
    expect(b.get()).toBeNull();
  });
});
