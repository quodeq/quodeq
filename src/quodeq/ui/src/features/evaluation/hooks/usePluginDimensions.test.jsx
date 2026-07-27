import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { ApiProvider } from '../../../api/ApiContext.jsx';

vi.mock('../../../utils/visibleStandards.js', () => ({
  readVisibleStandardIds: vi.fn(),
}));

const { readVisibleStandardIds } = await import('../../../utils/visibleStandards.js');
const { usePluginDimensions, invalidateDimensionCache } =
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
});
