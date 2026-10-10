import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { isPendingPayload } from '../../../api/scoresShape.js';
import { STALE_TIME_MS, refetchWhilePendingOrError } from '../../../hooks/queryDefaults.js';
import { useScopedPlaceholder } from '../../../hooks/useScopedPlaceholder.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

const EMPTY_TREND = [];

/**
 * The score history the dimension page charts. The dashboard's trend belongs
 * to the SELECTED project, so it is only valid when the page shows that
 * project: a cross-project entry (Compare's matrix, the attention list) opens
 * another project's dimension without changing the selection, and charting
 * the borrowed trend there drew the selected project's history under the
 * other project's score.
 *
 * `borrowedTrend` is the selected project's trend, or null when the page
 * shows another project; then the page reads that project's own latest
 * scores, under the same key the Overview uses so the two share one cache.
 */
export function useExplorerTrend(project, selectedSource, borrowedTrend) {
  const { getProjectScores, sharedGetProjectScores } = useApi();
  const fetchScores = selectedSource === PROJECT_SOURCE.SHARED ? sharedGetProjectScores : getProjectScores;
  const { projectKey } = useScopedPlaceholder(project, selectedSource);
  const ownQuery = useQuery({
    queryKey: projectKeys.scores(projectKey, null, selectedSource),
    queryFn: () => fetchScores(project),
    enabled: borrowedTrend === null && !!project,
    staleTime: STALE_TIME_MS,
    refetchInterval: refetchWhilePendingOrError,
  });
  if (borrowedTrend !== null) return borrowedTrend;
  const data = ownQuery.data;
  if (!data || isPendingPayload(data)) return EMPTY_TREND;
  return data.trend || EMPTY_TREND;
}
