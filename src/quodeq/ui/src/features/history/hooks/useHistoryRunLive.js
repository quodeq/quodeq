/**
 * Live data for an in-progress History row.
 *
 * Mounts a per-row SSE subscription via useRunEventStream and reactively
 * subscribes to the cache slots that subscription writes. Returns
 *
 *   { liveDims, plannedDimensions, hasScoredDimension }
 *
 * where liveDims is a `{ [dim]: <evaluation/<dim>.json payload> }` map
 * and plannedDimensions is the dim list the run was started against
 * (sourced from the most recent status event).
 *
 * The render switch (placeholder vs partial summary) lives in the
 * caller; this hook is just the data adapter.
 *
 * Gating: useRunEventStream itself is gated on VITE_USE_SSE_EVENTS,
 * so when the flag is off liveDims/plannedDimensions stay at their empty
 * defaults forever. hasScoredDimension does NOT depend on that flag: it
 * polls the same on-disk progress endpoint the running Evaluation page
 * uses (getEvaluationProgress), so a row's "ready to view" state reflects
 * real per-dimension completion even when SSE is off (the default) --
 * see quality-cycle discussion of the "No standards fully evaluated yet"
 * bug this fixes: hasScoredDims was previously only ever set from SSE
 * events, which never arrive with SSE off, so it stayed stuck at false
 * for a run's entire duration regardless of actual progress.
 */
import { useQuery } from '@tanstack/react-query';
import { useRunEventStream } from '../../evaluation/hooks/useRunEventStream.js';
import { getEvaluationProgress } from '../../../api/index.js';
import { NO_JOB_ID, evaluationKeys } from '../../../api/queryKeys.js';

const PROGRESS_POLL_MS = 3000;

// queryFn never runs (enabled: false); the cache is populated only by
// the SSE writer in useRunEventStream. useQuery is here for its
// subscription -- when setQueryData fires, this component rerenders.
const NEVER_QUERIED = () => {
  throw new Error('cache slot is SSE-fed; queryFn must not run');
};

/**
 * Live state for a run open in History: the dimensions scored so far, the ones
 * still planned, and whether at least one has finished.
 *
 * The dimension and status slots are fed by the SSE stream rather than
 * fetched; the progress read is polled unconditionally so the page still
 * advances with SSE off.
 *
 * @returns {{liveDims: object, plannedDimensions: string[], hasScoredDimension: boolean}}
 */
export function useHistoryRunLive(runId) {
  useRunEventStream(runId);

  const { data: liveDims = {} } = useQuery({
    queryKey: evaluationKeys.dimensions(runId || NO_JOB_ID),
    queryFn: NEVER_QUERIED,
    enabled: false,
    staleTime: Infinity,
  });

  const { data: status } = useQuery({
    queryKey: evaluationKeys.status(runId || NO_JOB_ID),
    queryFn: NEVER_QUERIED,
    enabled: false,
    staleTime: Infinity,
  });

  // Unconditional (SSE-independent) poll: a pure on-disk read of per-dim
  // state, same source the running Evaluation page's progress bar uses.
  const { data: progress } = useQuery({
    queryKey: [...evaluationKeys.evaluation(runId || NO_JOB_ID), 'historyProgress'],
    queryFn: () => getEvaluationProgress(runId),
    enabled: !!runId,
    staleTime: 0,
    refetchInterval: PROGRESS_POLL_MS,
    retry: false,
  });

  const plannedDimensions = Array.isArray(status?.dimensions)
    ? status.dimensions
    : [];

  const hasScoredDimension = Array.isArray(progress?.dimensions)
    && progress.dimensions.some((d) => d?.state === 'done');

  return { liveDims, plannedDimensions, hasScoredDimension };
}
