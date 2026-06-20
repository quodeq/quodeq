/**
 * Finding #477 – useScanData should use request() (with 30s timeout)
 * instead of a raw fetch() for the /api/projects/<id>/scan call.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

// Mock request so we can verify it is called for the projectId branch.
vi.mock('../../../api/request.js', () => ({
  BASE: '/api',
  request: vi.fn(),
}));

vi.mock('../../../api/index.js', () => ({
  scanPath: vi.fn(),
}));

import { request } from '../../../api/request.js';
import { useScanData } from './useScanData.js';

describe('#477 useScanData uses request() for projectId path', () => {
  beforeEach(() => {
    request.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls request() instead of raw fetch when projectId is given', async () => {
    request.mockResolvedValue({ branches: ['main'], currentBranch: 'main' });

    const { result } = renderHook(() => useScanData('proj-1'), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => {
      expect(result.current.scanData).toBeDefined();
    });

    expect(request).toHaveBeenCalled();
    const [path] = request.mock.calls[0];
    expect(path).toContain('/projects/proj-1/scan');
  });

  it('does not call raw fetch directly for the projectId branch', async () => {
    request.mockResolvedValue({ branches: ['main'] });
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    const { result } = renderHook(() => useScanData('proj-2'), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => {
      expect(result.current.scanData).toBeDefined();
    });

    // fetch should NOT have been called directly — only via request()
    // (which is itself mocked above and doesn't call fetch).
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
