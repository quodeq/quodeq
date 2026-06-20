import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useLibrary } from './useLibrary.js';

const fakeApi = {
  listLibrary: vi.fn(),
  importFromLibrary: vi.fn(),
};

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

describe('useLibrary', () => {
  beforeEach(() => {
    Object.values(fakeApi).forEach((fn) => fn.mockReset());
  });

  it('calls the injected listLibrary from ApiContext, not a hard import', async () => {
    fakeApi.listLibrary.mockResolvedValue([
      { id: 's1', name: 'Standard 1' },
      { id: 's2', name: 'Standard 2' },
    ]);
    const { result } = renderHook(() => useLibrary(), { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(result.current.libraryStandards).toHaveLength(2);
    });
    expect(fakeApi.listLibrary).toHaveBeenCalled();
    expect(result.current.error).toBeNull();
  });

  it('loads the library list on mount', async () => {
    fakeApi.listLibrary.mockResolvedValue([
      { id: 's1', name: 'Standard 1' },
      { id: 's2', name: 'Standard 2' },
    ]);
    const { result } = renderHook(() => useLibrary(), { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(result.current.libraryStandards).toHaveLength(2);
    });
    expect(result.current.error).toBeNull();
  });

  it('exposes the error message when listLibrary fails', async () => {
    fakeApi.listLibrary.mockRejectedValue(new Error('library down'));
    const { result } = renderHook(() => useLibrary(), { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(result.current.error).toBe('library down');
    });
  });

  it('importStandard calls the injected importFromLibrary from ApiContext', async () => {
    fakeApi.listLibrary.mockResolvedValue([]);
    fakeApi.importFromLibrary.mockResolvedValue({});
    const { result } = renderHook(() => useLibrary(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.importStandard('foo.yaml');
    });
    expect(fakeApi.importFromLibrary).toHaveBeenCalledWith('foo.yaml');
  });

  it('importStandard surfaces the import error and re-throws', async () => {
    fakeApi.listLibrary.mockResolvedValue([]);
    fakeApi.importFromLibrary.mockRejectedValue(new Error('cannot import'));
    const { result } = renderHook(() => useLibrary(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));

    let thrown = null;
    await act(async () => {
      try {
        await result.current.importStandard('foo.yaml');
      } catch (err) {
        thrown = err;
      }
    });
    expect(thrown?.message).toBe('cannot import');
    expect(result.current.error).toBe('cannot import');
  });
});
