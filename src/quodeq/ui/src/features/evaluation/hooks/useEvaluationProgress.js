import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEvaluationProgress } from '../../../api/index.js';
import { evaluationKeys } from '../../../api/queryKeys.js';

const POLL_INTERVAL_MS = 2000;

/**
 * Shared live-progress query for a run, used by both the stat strip
 * (`JobStatStrip`) and the progress bar (`ScanProgress`). They share the same
 * queryKey, so React Query collapses them into one cache entry — keeping this
 * in one hook removes the duplicated query and the duplicated terminal-refetch.
 *
 * Polls every POLL_INTERVAL_MS while the job is non-terminal. When the job
 * reaches a terminal state the poll stops — but the final flush of taken-file
 * counts often lands *between* the last running poll and the terminal
 * transition (in fast incremental/cached runs the last 2s window completes the
 * remaining files), so the cached value would freeze below 100% (the classic
 * "stuck at 97%"). To avoid that, fetch once more on the running→terminal edge
 * so the UI reflects the final counts.
 *
 * @param {string|undefined} jobId
 * @param {boolean} isTerminal  caller-derived (the two consumers use slightly
 *   different terminal-state sets, so the decision stays with them)
 */
export function useEvaluationProgress(jobId, isTerminal) {
  const query = useQuery({
    queryKey: jobId ? [...evaluationKeys.evaluation(jobId), 'progress'] : ['evaluation', '_none_', 'progress'],
    queryFn: () => getEvaluationProgress(jobId),
    enabled: !!jobId,
    refetchInterval: isTerminal ? false : POLL_INTERVAL_MS,
    staleTime: 0,
    retry: false,
  });

  const { refetch } = query;
  const settledRef = useRef(false);
  useEffect(() => {
    if (!jobId) return;
    if (isTerminal && !settledRef.current) {
      settledRef.current = true;
      refetch();
    } else if (!isTerminal) {
      // Reset for the next run/transition (e.g. a re-used component instance).
      settledRef.current = false;
    }
  }, [jobId, isTerminal, refetch]);

  return query;
}
