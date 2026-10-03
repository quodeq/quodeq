import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { useRunFindings } from './useRunFindings.js';

const payload = { dimensions: [{ dimension: 'security', violations: [{ req: 'R1', file: 'a.py', line: 1 }] }], summary: {} };

function setup(api) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }) => (
    <QueryClientProvider client={client}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>
  );
  return { client, wrapper };
}

describe('useRunFindings', () => {
  it('loads the run scores under the Explorer key and exposes the dimensions', async () => {
    const getRunScores = vi.fn(async () => payload);
    const { client, wrapper } = setup({ getRunScores });
    const { result } = renderHook(() => useRunFindings({ project: 'p1', runId: 'r1' }), { wrapper });

    expect(result.current.dimensions).toEqual([]);
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.dimensions).toHaveLength(1));
    expect(getRunScores).toHaveBeenCalledWith('p1', 'r1');
    expect(client.getQueryData(projectKeys.runScores('p1', 'r1'))).toBe(payload);
  });

  it('reads a shared project through the mirror', async () => {
    const getRunScores = vi.fn();
    const sharedGetRunScores = vi.fn(async () => payload);
    const { wrapper } = setup({ getRunScores, sharedGetRunScores });
    const { result } = renderHook(() => useRunFindings({ project: 'p1', runId: 'r1', source: 'shared' }), { wrapper });

    await waitFor(() => expect(result.current.dimensions).toHaveLength(1));
    expect(getRunScores).not.toHaveBeenCalled();
    expect(sharedGetRunScores).toHaveBeenCalledWith('p1', 'r1');
  });

  it('does not fetch without a run or when disabled', () => {
    const getRunScores = vi.fn();
    const { wrapper } = setup({ getRunScores });
    renderHook(() => useRunFindings({ project: 'p1', runId: null }), { wrapper });
    renderHook(() => useRunFindings({ project: 'p1', runId: 'r1', enabled: false }), { wrapper });
    expect(getRunScores).not.toHaveBeenCalled();
  });

  it('reports an error without throwing', async () => {
    const getRunScores = vi.fn(async () => { throw new Error('down'); });
    const { wrapper } = setup({ getRunScores });
    const { result } = renderHook(() => useRunFindings({ project: 'p1', runId: 'r1' }), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.dimensions).toEqual([]);
  });
});
