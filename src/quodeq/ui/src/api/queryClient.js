/**
 * Singleton QueryClient for the dashboard.
 *
 * Defaults:
 * - staleTime: 30s — most server data is fresh enough on reload.
 * - gcTime: 5min (library default) — kept long enough for screen-back navigation.
 * - retry: 1 — fail fast on real errors.
 * - refetchOnWindowFocus / refetchOnReconnect: true — natural recovery.
 * - networkMode: 'always' — the API is on 127.0.0.1, so the browser's online
 *   signal (its route to the internet) says nothing about whether a fetch
 *   can succeed. The library default gates every fetch on that signal: once
 *   the webview fires `offline` (Wi-Fi drop, sleep, VPN flip) each refetch
 *   parks as fetchStatus 'paused' until an `online` event that WebKit does
 *   not always deliver. A query that had already failed then keeps its
 *   error, and the Overview's "Failed to load dashboard data" line stays up
 *   for as long as the window lives, with the server answering the whole
 *   time (pinned by queryClient.localhost.test.jsx).
 *
 * Per-query overrides live at each useQuery call site (refetchInterval
 * for polling-driven sources; staleTime: Infinity when SSE owns updates).
 *
 * focusManager is driven by utils/appVisibility.js rather than the library's
 * own listener. No query sets refetchIntervalInBackground, so reporting the
 * window as unfocused is what stops every refetchInterval while the app is
 * hidden — including the health poll, which resumes on its next tick.
 */
import { QueryClient, focusManager } from "@tanstack/react-query";
import { isHidden, subscribeVisibility } from "../utils/appVisibility.js";

focusManager.setEventListener((handleFocus) => {
  handleFocus(!isHidden());
  return subscribeVisibility(() => handleFocus(!isHidden()));
});

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
      networkMode: "always",
    },
    mutations: {
      networkMode: "always",
    },
  },
});
