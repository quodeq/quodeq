/**
 * SSE → cache-update writer.
 *
 * Subscribes to /api/evaluations/<jobId>/events and writes each event
 * into the TanStack Query cache via setQueryData. Components consume
 * the cached data via useQuery, agnostic to whether it arrived via
 * initial GET, refetchInterval poll, or this SSE handler.
 *
 * Returns nothing — this hook is a side-effect.
 *
 * Gated by VITE_USE_SSE_EVENTS (default off). When off, components fall
 * back to useQuery's refetchInterval polling.
 *
 * Each cache write is preceded by a fire-and-forget cancelQueries on
 * the same key. This prevents an in-flight initial fetch (or poll)
 * from landing AFTER our setQueryData and overwriting the streamed
 * value — a real race once a query is mounted in the same render as
 * the SSE handler.
 */
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { evaluationKeys, projectKeys } from "../../../api/queryKeys.js";

// Cap the per-job findings array so a long-running scan with tens of thousands
// of findings does not grow the React Query cache without bound. The dashboard
// renders aggregated counts and the most-recent slice; older entries are still
// reachable through the scored evaluation/<dim>.json artifacts on disk.
const MAX_FINDINGS_IN_CACHE = 5000;
const TERMINAL_STATES = new Set(["done", "failed", "cancelled"]);

function isSseEnabled() {
  return import.meta.env?.VITE_USE_SSE_EVENTS === "true";
}

function appendBoundedFinding(prev, data) {
  if (prev.length >= MAX_FINDINGS_IN_CACHE) {
    const trimmed = prev.slice(prev.length - MAX_FINDINGS_IN_CACHE + 1);
    trimmed.push(data);
    return trimmed;
  }
  return [...prev, data];
}

export function useRunEventStream(jobId) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!isSseEnabled()) return undefined;
    if (!jobId) return undefined;

    const writeCache = (key, updater) => {
      queryClient.cancelQueries({ queryKey: key });
      queryClient.setQueryData(key, updater);
    };

    const source = new EventSource(`/api/evaluations/${jobId}/events`);

    source.addEventListener("status", (e) => {
      try {
        const data = JSON.parse(e.data);
        writeCache(evaluationKeys.status(jobId), data);
        if (data && TERMINAL_STATES.has(data.state)) {
          // Run just hit a terminal state -- the trend's view of this run is
          // about to flip from "in-progress / partial" to "terminal / final".
          // Invalidate the project subtree so the History row rerenders against
          // the freshly-fetched trend instead of staying on the SSE-fed live
          // dim cache for an unbounded time.
          queryClient.invalidateQueries({ queryKey: projectKeys.all() });
        }
      } catch {
        // ignore malformed frames; reconnect handles recovery via Last-Event-ID
      }
    });

    source.addEventListener("dimension-completed", (e) => {
      try {
        const data = JSON.parse(e.data);
        writeCache(
          evaluationKeys.dimensions(jobId),
          (prev = {}) => ({ ...prev, [data.dimension]: data }),
        );
      } catch {
        // ignore
      }
    });

    source.addEventListener("finding", (e) => {
      try {
        const data = JSON.parse(e.data);
        writeCache(
          evaluationKeys.findings(jobId),
          (prev = []) => appendBoundedFinding(prev, data),
        );
      } catch {
        // ignore
      }
    });

    source.addEventListener("done", () => {
      source.close();
    });

    return () => source.close();
  }, [jobId, queryClient]);
}
