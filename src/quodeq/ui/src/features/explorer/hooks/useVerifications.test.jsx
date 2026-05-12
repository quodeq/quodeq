import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useVerifications } from './useVerifications';

describe('useVerifications', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns empty map with loading=true initially, then loading=false on 404', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: false,
      status: 404,
    });

    const { result } = renderHook(() => useVerifications('eval-123'));

    // Initially loading
    expect(result.current.loading).toBe(true);
    expect(result.current.map.size).toBe(0);

    // After 404 response
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(result.current.map.size).toBe(0);
  });

  it('deduplicates verifications by finding_id, keeping newest first', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        verifications: [
          {
            verification_id: 'v-001',
            dimension: 'dim1',
            finding_id: 'f-123',
            verdict: 'APPLICABLE',
            confidence: 0.95,
            evidence_summary: 'newer',
            model: 'gpt-4',
            elapsed_ms: 1000,
            created_at: '2026-05-12T10:00:00Z',
          },
          {
            verification_id: 'v-002',
            dimension: 'dim1',
            finding_id: 'f-123',
            verdict: 'NOT_APPLICABLE',
            confidence: 0.5,
            evidence_summary: 'older',
            model: 'gpt-4',
            elapsed_ms: 800,
            created_at: '2026-05-12T09:00:00Z',
          },
          {
            verification_id: 'v-003',
            dimension: 'dim2',
            finding_id: 'f-456',
            verdict: 'FALSE_POSITIVE',
            confidence: 0.85,
            evidence_summary: 'distinct',
            model: 'gpt-4',
            elapsed_ms: 900,
            created_at: '2026-05-12T08:00:00Z',
          },
        ],
      }),
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
    expect(globalThis.fetch).not.toHaveBeenCalled();

    globalThis.fetch.mockClear();

    const { result: resultUndefined } = renderHook(() => useVerifications(undefined));
    expect(resultUndefined.current.map.size).toBe(0);
    expect(resultUndefined.current.loading).toBe(false);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('handles fetch errors gracefully', async () => {
    globalThis.fetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useVerifications('eval-789'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.map.size).toBe(0);
  });

  it('handles empty verifications array', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ verifications: [] }),
    });

    const { result } = renderHook(() => useVerifications('eval-empty'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.map.size).toBe(0);
  });

  it('cancels pending fetch when evalId changes', async () => {
    const abortSpy = vi.fn();
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        verifications: [
          {
            verification_id: 'v-001',
            dimension: 'dim1',
            finding_id: 'f-123',
            verdict: 'APPLICABLE',
            confidence: 0.95,
            evidence_summary: 'test',
            model: 'gpt-4',
            elapsed_ms: 1000,
            created_at: '2026-05-12T10:00:00Z',
          },
        ],
      }),
    });

    const { rerender } = renderHook(
      ({ evalId }) => useVerifications(evalId),
      { initialProps: { evalId: 'eval-123' } },
    );

    // Change evalId
    rerender({ evalId: 'eval-456' });

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith('/api/evaluations/eval-456/verifications');
    });
  });
});
