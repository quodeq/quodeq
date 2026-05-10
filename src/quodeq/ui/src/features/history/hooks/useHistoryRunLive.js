/**
 * Live data for an in-progress History row.
 *
 * Mounts a per-row SSE subscription via useRunEventStream and reactively
 * subscribes to the cache slots that subscription writes. Returns
 *
 *   { liveDims, plannedDimensions }
 *
 * where liveDims is a `{ [dim]: <evaluation/<dim>.json payload> }` map
 * and plannedDimensions is the dim list the run was started against
 * (sourced from the most recent status event).
 *
 * The render switch (placeholder vs partial summary) lives in the
 * caller; this hook is just the data adapter.
 *
 * Gating: useRunEventStream itself is gated on VITE_USE_SSE_EVENTS,
 * so when the flag is off this hook simply returns the empty defaults
 * forever. No behavior change for the SSE-off path.
 */
import { useQuery } from '@tanstack/react-query';
import { useRunEventStream } from '../../evaluation/hooks/useRunEventStream.js';
import { evaluationKeys } from '../../../api/queryKeys.js';

// queryFn never runs (enabled: false); the cache is populated only by
// the SSE writer in useRunEventStream. useQuery is here for its
// subscription -- when setQueryData fires, this component rerenders.
const NEVER_QUERIED = () => {
  throw new Error('cache slot is SSE-fed; queryFn must not run');
};

export function useHistoryRunLive(runId) {
  useRunEventStream(runId);

  const { data: liveDims = {} } = useQuery({
    queryKey: runId
      ? evaluationKeys.dimensions(runId)
      : ['evaluation', '_none_', 'dimensions'],
    queryFn: NEVER_QUERIED,
    enabled: false,
    staleTime: Infinity,
  });

  const { data: status } = useQuery({
    queryKey: runId
      ? evaluationKeys.status(runId)
      : ['evaluation', '_none_', 'status'],
    queryFn: NEVER_QUERIED,
    enabled: false,
    staleTime: Infinity,
  });

  const plannedDimensions = Array.isArray(status?.dimensions)
    ? status.dimensions
    : [];

  return { liveDims, plannedDimensions };
}
