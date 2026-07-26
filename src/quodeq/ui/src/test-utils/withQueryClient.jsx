/**
 * Test wrapper providing a fresh QueryClient per test.
 *
 * Usage:
 *   import { withQueryClient } from '../test-utils/withQueryClient.jsx';
 *   const { result } = renderHook(() => useFoo(), { wrapper: withQueryClient() });
 *
 * The fresh client uses retry: false and gcTime: 0 for determinism —
 * tests don't share cache state and failing queries fail fast.
 */
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiProvider } from "../api/ApiContext.jsx";

export function withQueryClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

/**
 * Rerender-safe query + api wrapper. Use this for ANY test that calls
 * rerender().
 *
 *   const { result, rerender } = renderHook(({ p }) => useFoo(p), {
 *     wrapper: withStableQueryApi(fakeApi), initialProps: { p: 'p1' },
 *   });
 *
 * The tempting idiom is a local `wrap()` helper called from inside the
 * wrapper:
 *
 *   function wrap(api, children) { const QC = withQueryClient(); ... }
 *   { wrapper: ({ children }) => wrap(fakeApi, children) }   // <-- BROKEN
 *
 * That calls withQueryClient() on every render, so `QC` is a NEW component
 * type each time. React unmounts and remounts the whole subtree, discarding
 * the QueryClient, the cache, and every query observer. On the initial render
 * that is harmless, which is why such tests pass — but the moment a test
 * rerenders, anything that depends on continuity across a render is silently
 * destroyed: placeholderData, isPlaceholderData, isFetching-with-data, and
 * any hook state. Tests asserting those behaviours then pass against broken
 * code (this is exactly how the project-switch placeholder bug initially
 * evaded its own regression tests).
 *
 * Building the wrapper ONCE, here, keeps the component type stable across
 * rerenders.
 */
export function withStableQueryApi(api) {
  const QC = withQueryClient();
  return function StableWrapper({ children }) {
    return (
      <QC>
        <ApiProvider value={api}>{children}</ApiProvider>
      </QC>
    );
  };
}
