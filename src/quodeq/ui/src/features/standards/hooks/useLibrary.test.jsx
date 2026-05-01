import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

vi.mock('../../../api/index.js', () => ({
  listLibrary: vi.fn(),
  importFromLibrary: vi.fn(),
}));

import { listLibrary, importFromLibrary } from '../../../api/index.js';
import { useLibrary } from './useLibrary.js';

describe('useLibrary', () => {
  beforeEach(() => {
    listLibrary.mockReset();
    importFromLibrary.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads the library list on mount', async () => {
    listLibrary.mockResolvedValue([
      { id: 's1', name: 'Standard 1' },
      { id: 's2', name: 'Standard 2' },
    ]);
    const { result } = renderHook(() => useLibrary(), { wrapper: withQueryClient() });
    await waitFor(() => {
      expect(result.current.libraryStandards).toHaveLength(2);
    });
    expect(result.current.error).toBeNull();
  });

  it('exposes the error message when listLibrary fails', async () => {
    listLibrary.mockRejectedValue(new Error('library down'));
    const { result } = renderHook(() => useLibrary(), { wrapper: withQueryClient() });
    await waitFor(() => {
      expect(result.current.error).toBe('library down');
    });
  });

  it('importStandard surfaces the import error and re-throws', async () => {
    listLibrary.mockResolvedValue([]);
    importFromLibrary.mockRejectedValue(new Error('cannot import'));
    const { result } = renderHook(() => useLibrary(), { wrapper: withQueryClient() });
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
