import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useScanEstimates } from './useScanEstimates.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

vi.mock('../../../api/request.js', () => ({
  request: vi.fn(),
}));
import { request } from '../../../api/request.js';

describe('useScanEstimates', () => {
  beforeEach(() => { request.mockReset(); });

  it('fetches the project estimates payload', async () => {
    const payload = {
      dimensions: { reliability: { count: 30, total: 1407, cached: 1377, excluded: 0, reason: 'diff' } },
      projectFiles: 5256, cachedFiles: 5226, changedFiles: 30,
    };
    request.mockResolvedValue(payload);
    const { result } = renderHook(() => useScanEstimates('proj-1'), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.estimates).toEqual(payload));
    expect(request).toHaveBeenCalledWith('/projects/proj-1/estimates', expect.anything());
  });

  it('does not fetch when disabled or without a project', () => {
    renderHook(() => useScanEstimates('proj-1', false), { wrapper: withQueryClient() });
    renderHook(() => useScanEstimates(null), { wrapper: withQueryClient() });
    expect(request).not.toHaveBeenCalled();
  });

  it('resolves to null estimates on errors (best-effort decoration)', async () => {
    request.mockRejectedValue(new Error('404'));
    const { result } = renderHook(() => useScanEstimates('proj-2'), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.estimates).toBeNull();
  });
});
