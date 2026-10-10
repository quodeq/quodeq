import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDismissedFindings } from './useDismissedFindings.js';
import { projectKeys } from '../../../api/queryKeys.js';

// The list is a project query: `loading` covers the first fetch (the tab
// shows bars, not "No dismissed findings"), a cached list renders at once,
// and a shared project reads the mirror endpoint.

function withQueryClient(seed) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  seed?.(queryClient);
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper, queryClient };
}

vi.mock('../../../api/index.js', () => ({
  listDismissedFindings: vi.fn(),
  restoreFinding: vi.fn(),
  restoreAllFindings: vi.fn(),
  deleteFinding: vi.fn(),
  deleteAllFindings: vi.fn(),
  sharedListDismissedFindings: vi.fn(),
}));

import { listDismissedFindings, sharedListDismissedFindings } from '../../../api/index.js';

const sampleA = { req: 'A1', file: 'a.py', line: 10, severity: 'minor', principle: 'P1' };

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDismissedFindings -- loading and the cached list', () => {
  it('reports loading until the first fetch resolves', async () => {
    let resolve;
    listDismissedFindings.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    const { result } = renderHook(
      () => useDismissedFindings({ selectedProject: 'proj', setRestoreError: vi.fn(), selectedSource: 'local' }),
      withQueryClient(),
    );
    expect(result.current.loading).toBe(true);
    expect(result.current.dismissed).toEqual([]);

    resolve([sampleA]);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.dismissed).toEqual([sampleA]);
  });

  it('renders a cached list at once, with no loading state', () => {
    const { wrapper } = withQueryClient((qc) => qc.setQueryData(projectKeys.dismissed('proj', 'local'), [sampleA]));
    listDismissedFindings.mockResolvedValue([sampleA]);
    const { result } = renderHook(
      () => useDismissedFindings({ selectedProject: 'proj', setRestoreError: vi.fn(), selectedSource: 'local' }),
      { wrapper },
    );
    expect(result.current.loading).toBe(false);
    expect(result.current.dismissed).toEqual([sampleA]);
  });

  it('reads a shared project from the mirror endpoint', async () => {
    sharedListDismissedFindings.mockResolvedValueOnce([sampleA]);
    const { result } = renderHook(
      () => useDismissedFindings({ selectedProject: 'proj', setRestoreError: vi.fn(), selectedSource: 'shared' }),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toEqual([sampleA]));
    expect(sharedListDismissedFindings).toHaveBeenCalledWith('proj');
    expect(listDismissedFindings).not.toHaveBeenCalled();
  });

  it('is idle with no project selected', () => {
    const { result } = renderHook(
      () => useDismissedFindings({ selectedProject: '', setRestoreError: vi.fn(), selectedSource: 'local' }),
      withQueryClient(),
    );
    expect(result.current.loading).toBe(false);
    expect(listDismissedFindings).not.toHaveBeenCalled();
  });
});
