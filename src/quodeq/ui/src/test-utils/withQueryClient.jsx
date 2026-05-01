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
