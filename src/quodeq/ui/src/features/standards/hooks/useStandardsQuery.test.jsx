import { describe, it, expect } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { useStandardsQuery } from './useStandardsQuery.js';

describe('useStandardsQuery', () => {
  it('returns the query data with no error once it loads', async () => {
    const { result } = renderHook(
      () => useStandardsQuery({ queryKey: ['sq-ok'], queryFn: () => Promise.resolve([1]) }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => expect(result.current.data).toEqual([1]));
    expect([result.current.isLoading, result.current.error]).toEqual([false, null]);
  });

  it('reports the failed query by its message', async () => {
    const { result } = renderHook(
      () => useStandardsQuery({ queryKey: ['sq-fail'], queryFn: () => Promise.reject(new Error('boom')), retry: false }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => expect(result.current.error).toBe('boom'));
  });

  it('prefers the last mutation error over the query error', async () => {
    const { result } = renderHook(
      () => useStandardsQuery({ queryKey: ['sq-mut'], queryFn: () => Promise.reject(new Error('boom')), retry: false }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => expect(result.current.error).toBe('boom'));
    act(() => result.current.setMutationError('save failed'));
    expect(result.current.error).toBe('save failed');
  });
});
