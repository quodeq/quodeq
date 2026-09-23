/**
 * Singleton QueryClient for the dashboard.
 *
 * Defaults:
 * - staleTime: 30s — most server data is fresh enough on reload.
 * - gcTime: 5min (library default) — kept long enough for screen-back navigation.
 * - retry: 1 — fail fast on real errors.
 * - refetchOnWindowFocus / refetchOnReconnect: true — natural recovery.
 *
 * Per-query overrides live at each useQuery call site (refetchInterval
 * for polling-driven sources; staleTime: Infinity when SSE owns updates).
 */
import { QueryClient } from "@tanstack/react-query";

// gcTime: 5min (library default) — kept long enough for screen-back
// navigation (see docstring above).
const GC_TIME_MINUTES = 5;
const MINUTE_MS = 60_000;

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: GC_TIME_MINUTES * MINUTE_MS,
      retry: 1,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
    },
  },
});
