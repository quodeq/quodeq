import { describe, it, expect } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { projectsKeys } from '../../api/queryKeys.js';
import { recordWarmupSnapshot, useWarmupSnapshot } from './warmupSnapshot.js';

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }) => createElement(QueryClientProvider, { client }, children);
  return { client, wrapper };
}

describe('warmupSnapshot', () => {
  it('reads null before the list recorded anything', () => {
    const { wrapper } = setup();
    const { result } = renderHook(() => useWarmupSnapshot(), { wrapper });
    expect(result.current).toBeNull();
  });

  it('a strip mounted after the first list sees the recorded snapshot', () => {
    const { client, wrapper } = setup();
    recordWarmupSnapshot(client, { active: true, projectsDone: 1, projectsTotal: 4, currentProjectName: 'quodeq' });
    const { result } = renderHook(() => useWarmupSnapshot(), { wrapper });
    expect(result.current).toEqual({ active: true, projectsDone: 1, projectsTotal: 4, currentProjectName: 'quodeq' });
  });

  it('re-renders when the list records a new snapshot, and null clears it', async () => {
    const { client, wrapper } = setup();
    const { result } = renderHook(() => useWarmupSnapshot(), { wrapper });
    act(() => recordWarmupSnapshot(client, { active: true, projectsDone: 0, projectsTotal: 2 }));
    await waitFor(() => expect(result.current?.active).toBe(true));
    act(() => recordWarmupSnapshot(client, undefined));
    await waitFor(() => expect(result.current).toBeNull());
    expect(client.getQueryData(projectsKeys.warmup())).toBeNull();
  });
});
