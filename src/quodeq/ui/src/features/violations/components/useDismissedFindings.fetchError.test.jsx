import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDismissedFindings } from './useDismissedFindings.js';

// Split out for cluster 25: the mount-time fetchDismissed() was the sole
// handler in this file skipping the console.error + setRestoreError
// convention every sibling mutation handler uses -- a failed load silently
// fell back to an empty list with no user-visible signal.

function withQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper };
}

vi.mock('../../../api/index.js', () => ({
  listDismissedFindings: vi.fn(),
  restoreFinding: vi.fn(),
  restoreAllFindings: vi.fn(),
  deleteFinding: vi.fn(),
  deleteAllFindings: vi.fn(),
  sharedListDismissedFindings: vi.fn(),
}));

import { listDismissedFindings } from '../../../api/index.js';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDismissedFindings -- fetch failure on mount', () => {
  it('logs and sets restoreError when the dismissed list fails to load, still falling back to []', async () => {
    const err = new Error('network down');
    listDismissedFindings.mockRejectedValueOnce(err);
    const setRestoreError = vi.fn();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { result } = renderHook(
      () => useDismissedFindings({ selectedProject: 'proj', onRefresh: vi.fn(), setRestoreError, refreshKey: 0, selectedSource: 'local' }),
      withQueryClient(),
    );

    await waitFor(() => expect(setRestoreError).toHaveBeenCalledTimes(1));
    expect(errorSpy).toHaveBeenCalledWith('Failed to load dismissed findings:', err);
    expect(result.current.dismissed).toEqual([]);

    errorSpy.mockRestore();
  });
});
