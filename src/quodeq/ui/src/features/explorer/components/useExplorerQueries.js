import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { useScopedPlaceholder } from '../../../hooks/useScopedPlaceholder.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

/**
 * The two react-query subscriptions useExplorerData composes: the
 * dimension eval and the run's rescore data, both scoped to
 * project+source (samePlaceholderScope) so a run-navigator swap keeps
 * stale data visible via isFetching, while a project switch drops to the
 * real LoadingScreen. Also re-pulls the rescore data whenever
 * `refreshSignal` (the dashboard payload identity) changes.
 */
export function useExplorerQueries(project, dimension, runId, refreshSignal, selectedSource) {
  const { getDimensionEval, getRunScores, sharedGetDimensionEval, sharedGetRunScores } = useApi();
  const fetchDimensionEval = selectedSource === PROJECT_SOURCE.SHARED ? sharedGetDimensionEval : getDimensionEval;
  const fetchRunScores = selectedSource === PROJECT_SOURCE.SHARED ? sharedGetRunScores : getRunScores;
  const queryClient = useQueryClient();
  const { projectKey, keepInScope } = useScopedPlaceholder(project, selectedSource);

  const evalQuery = useQuery({
    queryKey: projectKeys.dimensionEval(projectKey, runId, dimension, selectedSource),
    queryFn: () => fetchDimensionEval(project, runId, dimension),
    enabled: !!project && !!dimension,
    staleTime: 60_000,
    placeholderData: keepInScope,
  });

  // The rescore side. Non-fatal by design: if it errors, the page renders
  // the unrescored eval (the old fetchAndRescore caught and dropped scores
  // errors the same way).
  const scoresQuery = useQuery({
    queryKey: projectKeys.runScores(projectKey, runId, selectedSource),
    queryFn: () => fetchRunScores(project, runId),
    enabled: !!project,
    staleTime: 60_000,
    placeholderData: keepInScope,
  });

  const initialRef = useRef(refreshSignal);
  useEffect(() => {
    if (refreshSignal === initialRef.current) return;
    if (!project || !runId) return;
    queryClient.invalidateQueries({ queryKey: projectKeys.runScores(projectKey, runId, selectedSource) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSignal]);

  return { evalQuery, scoresQuery };
}
