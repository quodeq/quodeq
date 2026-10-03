import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useFullRunDimensions } from './useFullRunDimensions.js';
import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';

const wrap = (getRunScores) => withStableQueryApi({ getRunScores });

describe('useFullRunDimensions', () => {
  it('returns the given dimensions when they carry bodies', () => {
    const getRunScores = vi.fn();
    const dims = [{ dimension: 'security', violations: [] }];
    const { result } = renderHook(
      () => useFullRunDimensions({ project: 'p1', runId: 'r1', source: 'local', dimensions: dims }),
      { wrapper: wrap(getRunScores) },
    );
    expect(result.current).toBe(dims);
    expect(getRunScores).not.toHaveBeenCalled();
  });

  it('reads the run findings when the given dimensions are slim', async () => {
    const getRunScores = vi.fn(async () => ({ dimensions: [{ dimension: 'security', violations: [{ req: 'S-1', severity: 'major' }] }] }));
    const { result } = renderHook(
      () => useFullRunDimensions({ project: 'p1', runId: 'r1', source: 'local', dimensions: [{ dimension: 'security' }] }),
      { wrapper: wrap(getRunScores) },
    );
    await waitFor(() => expect(result.current[0]?.violations).toHaveLength(1));
    expect(getRunScores).toHaveBeenCalledWith('p1', 'r1');
  });

  it('returns an empty list while the findings load', () => {
    const getRunScores = vi.fn(() => new Promise(() => {}));
    const { result } = renderHook(
      () => useFullRunDimensions({ project: 'p1', runId: 'r1', source: 'local', dimensions: [{ dimension: 'security' }] }),
      { wrapper: wrap(getRunScores) },
    );
    expect(result.current).toEqual([]);
  });
});
