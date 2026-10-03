import { describe, it, expect, vi } from 'vitest';
import { render, renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectKeys } from '../api/queryKeys.js';
import { useCompareData } from '../features/compare/hooks/useCompareData.js';
import { cacheEntries, countCommits, countFetches } from './budgets.jsx';

// The helpers are what the budget tests lean on, so each is pinned here on
// a plain component and a plain cache; the compare case is the first real
// request budget: 10 projects on the Compare tab cost exactly 1 request
// (10 cache entries), and a second visit with fresh data costs none.

const FLEET_SIZE = 10;
const FLEET = Array.from({ length: FLEET_SIZE }, (unused, i) => ({ name: `p${i}` }));

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
}

function Label({ text }) {
  return <span>{text}</span>;
}

describe('countCommits', () => {
  it('counts every commit of the wrapped component and resets', () => {
    const label = countCommits(Label);
    const { rerender } = render(<label.Counted text="a" />);
    rerender(<label.Counted text="b" />);
    expect(label.commits()).toBe(2);
    label.reset();
    rerender(<label.Counted text="c" />);
    expect(label.commits()).toBe(1);
  });
});

describe('countFetches', () => {
  it('counts fetch starts, groups them by key, and stops listening', async () => {
    const client = makeClient();
    const fetches = countFetches(client);
    await client.fetchQuery({ queryKey: projectKeys.scores('p1', null), queryFn: async () => 1 });
    await client.fetchQuery({ queryKey: projectKeys.scores('p2', null), queryFn: async () => 2 });
    expect(fetches.count()).toBe(2);
    expect(Object.values(fetches.byKey()).reduce((a, b) => a + b, 0)).toBe(2);
    fetches.stop();
    await client.fetchQuery({ queryKey: projectKeys.scores('p3', null), queryFn: async () => 3 });
    expect(fetches.count()).toBe(2);
  });
});

describe('cacheEntries', () => {
  it('matches entries by key prefix', () => {
    const client = makeClient();
    client.setQueryData(projectKeys.scores('p1', null), {});
    client.setQueryData(projectKeys.scores('p1', 'r1'), {});
    client.setQueryData(projectKeys.scores('p2', null), {});
    expect(cacheEntries(client, projectKeys.scores('p1', null).slice(0, 2))).toHaveLength(2);
    expect(cacheEntries(client)).toHaveLength(3);
  });
});

describe('compare request budget', () => {
  it('a fleet of 10 costs 1 request once and 0 on the next visit', async () => {
    const client = makeClient();
    const api = {
      getFleetCompare: vi.fn(async (ids) => ({ summaries: ids.map((id) => ({ project: id })), errors: {} })),
      sharedGetFleetCompare: vi.fn(),
    };
    const fetches = countFetches(client);
    const wrapper = ({ children }) => (
      <QueryClientProvider client={client}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>
    );

    const first = renderHook(() => useCompareData(FLEET), { wrapper });
    await waitFor(() => expect(first.result.current.allLoaded).toBe(true));
    expect(fetches.count()).toBe(FLEET_SIZE);
    expect(api.getFleetCompare).toHaveBeenCalledTimes(1);
    expect(api.getFleetCompare).toHaveBeenCalledWith(FLEET.map((p) => p.name));
    expect(api.sharedGetFleetCompare).not.toHaveBeenCalled();
    first.unmount();

    fetches.reset();
    const second = renderHook(() => useCompareData(FLEET), { wrapper });
    await act(async () => {});
    expect(second.result.current.allLoaded).toBe(true);
    expect(fetches.count()).toBe(0);
    fetches.stop();
  });
});
