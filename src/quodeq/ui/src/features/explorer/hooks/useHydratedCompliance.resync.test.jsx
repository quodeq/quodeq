import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { STALE_TIME_MS } from '../../../hooks/queryDefaults.js';
import { useHydratedFindings, resetDetailResyncForTests } from './useHydratedCompliance.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';

// The File and Principle pages render the rows their detail query returns;
// the list payload they were opened from only says what to ask for. When
// that payload names a finding the detail no longer has at its file and
// line, the page already shows the server's rows, and the project's queries
// are refreshed once per staleness window so the rest of the page catches
// up. Opening a page over a payload older than its staleness window
// refreshes it too, instead of waiting for a miss.
const ref = { project: 'proj', asOf: null, dimension: 'security', kind: 'violation' };
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

const projectInvalidations = (invalidate) =>
  invalidate.mock.calls.filter(([arg]) => arg?.queryKey?.join() === projectKeys.project('proj', 'local').join());

beforeEach(() => resetDetailResyncForTests());

describe('useHydratedFindings over a payload that fell behind', () => {
  it('renders the server rows and refreshes the project once', async () => {
    const get = vi.fn(async () => [{ ...slim('a.py', 12, 'New title'), detailDeferred: false, reason: 'why', snippet: 'code' }]);
    const items = [slim('a.py', 10, 'Old title'), slim('b.py', 3)];
    const { wrapper, invalidate } = setup(get, { scoresUpdatedAt: Date.now() });
    const { result, rerender } = renderHook(() => useHydratedFindings(items, FINDING_TYPE.VIOLATION), { wrapper });

    await waitFor(() => expect(result.current).toHaveLength(1));
    expect(result.current[0]).toMatchObject({ title: 'New title', line: 12, reason: 'why', detailDeferred: false });
    await waitFor(() => expect(projectInvalidations(invalidate)).toHaveLength(1));
    rerender();
    rerender();
    expect(projectInvalidations(invalidate)).toHaveLength(1);
  });

  it('does not refresh when every item still has its row', async () => {
    const item = slim('a.py', 10);
    const get = vi.fn(async () => [{ ...item, detailDeferred: false, reason: 'why', snippet: 'code' }]);
    const { wrapper, invalidate } = setup(get, { scoresUpdatedAt: Date.now() });
    const { result } = renderHook(() => useHydratedFindings([item], FINDING_TYPE.VIOLATION), { wrapper });

    await waitFor(() => expect(result.current[0].snippet).toBe('code'));
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('refreshes a payload older than the staleness window when the page opens', async () => {
    const item = slim('a.py', 10);
    const get = vi.fn(async () => [{ ...item, detailDeferred: false, reason: 'why', snippet: 'code' }]);
    const { wrapper, invalidate } = setup(get, { scoresUpdatedAt: Date.now() - STALE_TIME_MS - 1000 });
    renderHook(() => useHydratedFindings([item], FINDING_TYPE.VIOLATION), { wrapper });

    await waitFor(() => expect(projectInvalidations(invalidate)).toHaveLength(1));
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
