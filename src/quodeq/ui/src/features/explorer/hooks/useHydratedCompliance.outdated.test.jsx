import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { STALE_TIME_MS } from '../../../hooks/queryDefaults.js';
import { useHydratedFindings, resetDetailResyncForTests } from './useHydratedCompliance.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';

// The File and Principle pages render a snapshot of findings built when the
// user clicked, while the detail is fetched from the server's current state.
// A finding re-reported since (new title, shifted lines) has no detail row:
// the item is marked outdated, and the project's scores are invalidated once
// so the snapshot catches up. Opening a page over a payload older than its
// staleness window refreshes it too, instead of waiting for a miss.
const ref = { project: 'proj', asOf: null, dimension: 'security', generation: 7, kind: 'violation' };
const slim = (file, line, title = 'bad') => ({
  file, line, endLine: null, principle: 'P1', title,
  reason: null, snippet: null, context: null, detailDeferred: true, detailRef: ref,
});

function setup(getFindingDetail, { scoresUpdatedAt } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (scoresUpdatedAt !== undefined) {
    client.setQueryData(projectKeys.scores('proj', null, 'local'), { accumulated: { dimensions: [] } }, { updatedAt: scoresUpdatedAt });
  }
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }) => (
    <QueryClientProvider client={client}>
      <ApiProvider value={{ getFindingDetail, sharedGetFindingDetail: vi.fn() }}>{children}</ApiProvider>
    </QueryClientProvider>
  );
  return { wrapper, invalidate };
}

beforeEach(() => resetDetailResyncForTests());

describe('useHydratedFindings with a stale snapshot', () => {
  it('marks an item with no detail row as outdated and invalidates the project once', async () => {
    const get = vi.fn(async () => [{ ...slim('a.py', 12, 'New title'), detailDeferred: false, reason: 'why', snippet: 'code' }]);
    const items = [slim('a.py', 10, 'Old title'), slim('b.py', 3)];
    const { wrapper, invalidate } = setup(get, { scoresUpdatedAt: Date.now() });
    const { result, rerender } = renderHook(() => useHydratedFindings(items, FINDING_TYPE.VIOLATION), { wrapper });

    await waitFor(() => expect(result.current[0].detailOutdated).toBe(true));
    expect(result.current[0].detailDeferred).toBe(false);
    expect(result.current[0].reason).toBeNull();
    expect(result.current[1].detailOutdated).toBe(true);
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: projectKeys.project('proj', 'local') }));
    rerender();
    rerender();
    expect(invalidate.mock.calls.filter(([arg]) => arg?.queryKey?.join() === projectKeys.project('proj', 'local').join())).toHaveLength(1);
  });

  it('does not invalidate when every item found its detail', async () => {
    const item = slim('a.py', 10);
    const get = vi.fn(async () => [{ ...item, detailDeferred: false, reason: 'why', snippet: 'code' }]);
    const { wrapper, invalidate } = setup(get, { scoresUpdatedAt: Date.now() });
    const { result } = renderHook(() => useHydratedFindings([item], FINDING_TYPE.VIOLATION), { wrapper });

    await waitFor(() => expect(result.current[0].snippet).toBe('code'));
    expect(result.current[0].detailOutdated).toBeUndefined();
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('refreshes a payload older than the staleness window when the page opens', async () => {
    const item = slim('a.py', 10);
    const get = vi.fn(async () => [{ ...item, detailDeferred: false, reason: 'why', snippet: 'code' }]);
    const { wrapper, invalidate } = setup(get, { scoresUpdatedAt: Date.now() - STALE_TIME_MS - 1000 });
    renderHook(() => useHydratedFindings([item], FINDING_TYPE.VIOLATION), { wrapper });

    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: projectKeys.project('proj', 'local') }));
  });

  it('leaves a fresh payload alone when the page opens', async () => {
    const item = slim('a.py', 10);
    const get = vi.fn(async () => [{ ...item, detailDeferred: false, reason: 'why', snippet: 'code' }]);
    const { wrapper, invalidate } = setup(get, { scoresUpdatedAt: Date.now() });
    const { result } = renderHook(() => useHydratedFindings([item], FINDING_TYPE.VIOLATION), { wrapper });

    await waitFor(() => expect(result.current[0].snippet).toBe('code'));
    expect(invalidate).not.toHaveBeenCalled();
  });
});
