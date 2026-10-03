import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { useScopedPlaceholder } from '../../../hooks/useScopedPlaceholder.js';
import { isFrozenRun } from '../../../models/runRules.js';
import { STALE_TIME_MS, refetchWhileError } from '../../../hooks/queryDefaults.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

const EMPTY = [];

/**
 * One run's rescored dimensions with their finding lists (detail deferred,
 * see api/complianceDetail.js), for the run page: the worst-files table,
 * the hero navigation, the report and the fix plan read them; the dashboard
 * itself is the overview shape (counts only).
 *
 * Shares `projectKeys.runScores` with the Explorer's rescore merge, so a
 * visited dimension page has already warmed it and a dismiss splices both.
 *
 * @param {{project: string, runId: string, source?: string, availableRuns?: Array, enabled?: boolean}} opts
 * @returns {{dimensions: Array, isLoading: boolean, isError: boolean}}
 *   `dimensions` is [] until loaded.
 */
export function useRunFindings({ project, runId, source = PROJECT_SOURCE.LOCAL, availableRuns, enabled = true }) {
  const { getRunScores, sharedGetRunScores } = useApi();
  const fetchRunScores = source === PROJECT_SOURCE.SHARED ? sharedGetRunScores : getRunScores;
  const { projectKey } = useScopedPlaceholder(project, source);
  const query = useQuery({
    queryKey: projectKeys.runScores(projectKey, runId, source),
    queryFn: () => fetchRunScores(project, runId),
    enabled: enabled && !!project && !!runId,
    // A finished run only changes through mutations, which patch or
    // invalidate this entry (see api/applyMutationDelta.js).
    staleTime: isFrozenRun(runId, availableRuns) ? Infinity : STALE_TIME_MS,
    refetchInterval: refetchWhileError,
  });
  return { dimensions: query.data?.dimensions || EMPTY, isLoading: query.isLoading, isError: query.isError };
}
