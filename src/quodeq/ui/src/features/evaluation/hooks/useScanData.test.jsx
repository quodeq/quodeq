import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

vi.mock('../../../api/index.js', () => ({
  scanPath: vi.fn(),
}));

import { scanPath } from '../../../api/index.js';
import { useScanData } from './useScanData.js';

describe('useScanData', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
    scanPath.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns null scanData when neither id nor path given', () => {
    const { result } = renderHook(() => useScanData(null, null), { wrapper: withQueryClient() });
    expect(result.current.scanData).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('fetches /api/projects/<id>/scan when projectId is given', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ branches: ['main'], currentBranch: 'main' }),
    });
    const { result } = renderHook(() => useScanData('proj-1'), { wrapper: withQueryClient() });
    await waitFor(() => {
      expect(result.current.scanData).toEqual({ branches: ['main'], currentBranch: 'main' });
    });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/projects/proj-1/scan',
      expect.objectContaining({ signal: expect.anything() }),
    );
  });

  it('falls back to scanPath() when only localPath is given', async () => {
    scanPath.mockResolvedValue({ branches: ['dev'] });
    const { result } = renderHook(() => useScanData(null, '/tmp/repo'), { wrapper: withQueryClient() });
    await waitFor(() => {
      expect(result.current.scanData).toEqual({ branches: ['dev'] });
    });
    expect(scanPath).toHaveBeenCalledWith('/tmp/repo');
  });

  it('exposes error message when fetch fails', async () => {
    globalThis.fetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    const { result } = renderHook(() => useScanData('proj-2'), { wrapper: withQueryClient() });
    await waitFor(() => {
      expect(result.current.error).toMatch(/500/);
    });
  });
});
