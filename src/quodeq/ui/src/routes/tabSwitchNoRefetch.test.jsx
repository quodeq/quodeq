import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { projectKeys } from '../api/queryKeys.js';
import { useViolationsTabKeyReset } from '../features/violations/hooks/useViolationsPageState.js';
import { createPageStateCache } from '../utils/pageStateCache.js';
import { countFetches } from '../test-utils/budgets.jsx';

// Switching Overview -> History -> Violations -> Overview with fresh data
// must fire no request. Each tab mounts an observer on the query it reads
// (Violations also its tab-key reset, which used to invalidate on mount);
// the seeded cache is fresh, so the only way a fetch can happen is a
// mount-time invalidation.

const PROJECT = 'p1';
const SOURCE = 'local';
const KEYS = {
  dashboard: projectKeys.dashboard(PROJECT, null, SOURCE),
  scores: projectKeys.scores(PROJECT, null, SOURCE),
};

function makeClient(fetchSpy) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: Infinity, queryFn: fetchSpy } },
  });
  for (const key of Object.values(KEYS)) client.setQueryData(key, { seeded: true });
  return client;
}

function Overview() {
  useQuery({ queryKey: KEYS.dashboard });
  useQuery({ queryKey: KEYS.scores });
  return null;
}

function History() {
  useQuery({ queryKey: KEYS.scores });
  return null;
}

function Violations({ cache }) {
  useViolationsTabKeyReset({ tabKey: 1, selectedProject: PROJECT, cache });
  useQuery({ queryKey: KEYS.dashboard });
  return null;
}

describe('tab switches with fresh data', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('fire no request and leave no query invalidated', async () => {
    const fetchSpy = vi.fn(async () => ({ fetched: true }));
    const client = makeClient(fetchSpy);
    const fetches = countFetches(client);
    const cache = createPageStateCache();
    const wrap = (page) => <QueryClientProvider client={client}>{page}</QueryClientProvider>;

    const { rerender } = render(wrap(<Overview />));
    for (const page of [<History key="h" />, <Violations key="v" cache={cache} />, <Overview key="o" />]) {
      rerender(wrap(page));
      await act(async () => { await vi.runAllTimersAsync(); });
    }

    expect(fetches.byKey()).toEqual({});
    expect(fetchSpy).not.toHaveBeenCalled();
    fetches.stop();
    for (const key of Object.values(KEYS)) {
      expect(client.getQueryState(key).isInvalidated).toBe(false);
      expect(client.getQueryState(key).data).toEqual({ seeded: true });
    }
  });
});
