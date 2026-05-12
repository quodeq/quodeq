import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useVerifications } from './useVerifications';
import * as ApiContext from '../../../api/ApiContext.jsx';

describe('useVerifications', () => {
  let mockListVerifications;

  beforeEach(() => {
    mockListVerifications = vi.fn();
    vi.spyOn(ApiContext, 'useApi').mockReturnValue({
      listVerifications: mockListVerifications,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns empty map with loading=true initially, then loading=false on error', async () => {
    mockListVerifications.mockRejectedValue(new Error('404'));

    const { result } = renderHook(() => useVerifications('eval-123'));

    // Initially loading
    expect(result.current.loading).toBe(true);
    expect(result.current.map.size).toBe(0);

    // After error response
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(result.current.map.size).toBe(0);
  });

  it('deduplicates verifications by finding_id, keeping newest first', async () => {
    mockListVerifications.mockResolvedValue({
      verifications: [
        {
          finding_id: 'f-123',
          verdict: 'APPLICABLE',
          confidence: 0.95,
        },
        {
          finding_id: 'f-123',
          verdict: 'NOT_APPLICABLE',
          confidence: 0.5,
        },
        {
          finding_id: 'f-456',
          verdict: 'FALSE_POSITIVE',
          confidence: 0.85,
        },
      ],
    });

    const { result } = renderHook(() => useVerifications('eval-456'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // f-123 should have the newest verdict
    expect(result.current.map.get('f-123')).toEqual({
      verdict: 'APPLICABLE',
      confidence: 0.95,
    });

    // f-456 should be present
    expect(result.current.map.get('f-456')).toEqual({
      verdict: 'FALSE_POSITIVE',
      confidence: 0.85,
    });

    // Only 2 entries (deduped)
    expect(result.current.map.size).toBe(2);
  });

  it('returns empty map with loading=false when evalId is null or undefined', async () => {
    const { result: resultNull } = renderHook(() => useVerifications(null));
    expect(resultNull.current.map.size).toBe(0);
    expect(resultNull.current.loading).toBe(false);
    expect(mockListVerifications).not.toHaveBeenCalled();

    mockListVerifications.mockClear();

    const { result: resultUndefined } = renderHook(() => useVerifications(undefined));
    expect(resultUndefined.current.map.size).toBe(0);
    expect(resultUndefined.current.loading).toBe(false);
    expect(mockListVerifications).not.toHaveBeenCalled();
  });

  it('handles fetch errors gracefully', async () => {
    mockListVerifications.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useVerifications('eval-789'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.map.size).toBe(0);
  });

  it('handles empty verifications array', async () => {
    mockListVerifications.mockResolvedValue({ verifications: [] });

    const { result } = renderHook(() => useVerifications('eval-empty'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.map.size).toBe(0);
  });

  it('suppresses stale data when evalId changes before first promise resolves', async () => {
    // Create two deferred promises we can control
    let resolveFirstCall, resolveSecondCall;
    const firstPromise = new Promise((resolve) => {
      resolveFirstCall = resolve;
    });
    const secondPromise = new Promise((resolve) => {
      resolveSecondCall = resolve;
    });

    let callCount = 0;
    mockListVerifications.mockImplementation(() => {
      callCount++;
      return callCount === 1 ? firstPromise : secondPromise;
    });

    const { rerender, result } = renderHook(
      ({ evalId }) => useVerifications(evalId),
      { initialProps: { evalId: 'eval-A' } },
    );

    expect(result.current.loading).toBe(true);

    // Re-render with eval-B before eval-A resolves
    rerender({ evalId: 'eval-B' });

    // Resolve eval-A with its verifications (should be ignored)
    resolveFirstCall({
      verifications: [
        { finding_id: 'f-only-in-a', verdict: 'APPLICABLE', confidence: 0.9 },
      ],
    });

    // Resolve eval-B with its verifications
    resolveSecondCall({
      verifications: [
        { finding_id: 'f-only-in-b', verdict: 'FALSE_POSITIVE', confidence: 0.8 },
      ],
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Map should only contain eval-B's data (no leak from stale eval-A response)
    expect(result.current.map.size).toBe(1);
    expect(result.current.map.get('f-only-in-b')).toEqual({
      verdict: 'FALSE_POSITIVE',
      confidence: 0.8,
    });
    expect(result.current.map.has('f-only-in-a')).toBe(false);
  });
});
