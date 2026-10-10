import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { useExplorerTrend } from './useExplorerTrend.js';

const SELECTED_TREND = [{ runId: 'sel-1', dimensionDetails: [{ dimension: 'security', score: 8.7 }] }];
const OWN_TREND = [{ runId: 'own-1', dimensionDetails: [{ dimension: 'security', score: 2.2 }] }];

function fakeApi() {
  return {
    getProjectScores: vi.fn(async () => ({ trend: OWN_TREND })),
    sharedGetProjectScores: vi.fn(async () => ({ trend: OWN_TREND })),
  };
}

// A cross-project entry (Compare's matrix) opens another project's dimension
// without changing the selection: charting the selection's trend there drew
// the selected project's history under the other project's score.
describe('useExplorerTrend', () => {
  it('charts the selected project trend it was handed, without fetching', () => {
    const api = fakeApi();
    const { result } = renderHook(
      () => useExplorerTrend('quodeq', PROJECT_SOURCE.LOCAL, SELECTED_TREND),
      { wrapper: withStableQueryApi(api) },
    );
    expect(result.current).toBe(SELECTED_TREND);
    expect(api.getProjectScores).not.toHaveBeenCalled();
  });

  it('reads its own project history when handed none', async () => {
    const api = fakeApi();
    const { result } = renderHook(
      () => useExplorerTrend('benchmark', PROJECT_SOURCE.LOCAL, null),
      { wrapper: withStableQueryApi(api) },
    );
    expect(result.current).toEqual([]);
    await waitFor(() => expect(result.current).toEqual(OWN_TREND));
    expect(api.getProjectScores).toHaveBeenCalledWith('benchmark');
  });

  it('reads a shared project history from the shared source', async () => {
    const api = fakeApi();
    const { result } = renderHook(
      () => useExplorerTrend('remote', PROJECT_SOURCE.SHARED, null),
      { wrapper: withStableQueryApi(api) },
    );
    await waitFor(() => expect(result.current).toEqual(OWN_TREND));
    expect(api.sharedGetProjectScores).toHaveBeenCalledWith('remote');
    expect(api.getProjectScores).not.toHaveBeenCalled();
  });
});
