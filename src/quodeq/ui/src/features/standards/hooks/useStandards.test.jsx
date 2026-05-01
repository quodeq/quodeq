import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useStandards, STANDARD_TYPES } from './useStandards.js';

const fakeApi = {
  listStandards: vi.fn(),
  deleteStandard: vi.fn(),
  duplicateStandard: vi.fn(),
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

describe('useStandards', () => {
  beforeEach(() => {
    Object.values(fakeApi).forEach((fn) => fn.mockReset());
  });

  it('fetches standards on mount and groups them by type', async () => {
    fakeApi.listStandards.mockResolvedValue([
      { id: 'a', name: 'A', type: STANDARD_TYPES.BUILTIN },
      { id: 'b', name: 'B', type: STANDARD_TYPES.CUSTOM },
      { id: 'c', name: 'C', type: STANDARD_TYPES.CUSTOM },
    ]);
    const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(result.current.standards).toHaveLength(3);
    });
    expect(result.current.grouped[STANDARD_TYPES.BUILTIN]).toHaveLength(1);
    expect(result.current.grouped[STANDARD_TYPES.CUSTOM]).toHaveLength(2);
    expect(result.current.error).toBeNull();
  });

  it('exposes the error message when listStandards rejects', async () => {
    fakeApi.listStandards.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(result.current.error).toBe('boom');
    });
  });

  it('handleDelete calls deleteStandard and refreshes', async () => {
    fakeApi.listStandards.mockResolvedValue([{ id: 'a', name: 'A', type: STANDARD_TYPES.CUSTOM }]);
    fakeApi.deleteStandard.mockResolvedValue({});
    const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.standards).toHaveLength(1));
    await act(async () => {
      await result.current.handleDelete('a');
    });
    expect(fakeApi.deleteStandard).toHaveBeenCalledWith('a');
    // refresh triggers a refetch
    expect(fakeApi.listStandards.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('handleDelete surfaces the mutation error', async () => {
    fakeApi.listStandards.mockResolvedValue([]);
    fakeApi.deleteStandard.mockRejectedValue(new Error('cannot delete'));
    const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.handleDelete('a');
    });
    expect(result.current.error).toBe('cannot delete');
  });
});
