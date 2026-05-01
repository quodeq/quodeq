/**
 * Singleton QueryClient for the dashboard.
 *
 * Defaults match the Plan 3 spec:
 * - staleTime: 30s — most server data is fresh enough on reload.
 * - gcTime: 5min (library default) — kept long enough for screen-back navigation.
 * - retry: 1 — fail fast on real errors.
 * - refetchOnWindowFocus / refetchOnReconnect: true — natural recovery.
 *
 * Per-query overrides live at each useQuery call site (refetchInterval
 * for polling-driven sources; staleTime: Infinity when SSE owns updates).
 */
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
    },
  },
});
