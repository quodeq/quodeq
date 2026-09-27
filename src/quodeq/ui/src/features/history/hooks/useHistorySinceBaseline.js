/**
 * The since-baseline summary of the run highlighted on the History page.
 * The dashboard payload describes the Overview's run, so the History row
 * needs its own diff request, reduced to the same map the Overview folds.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { filterSinceBaseline, reduceDiffToSinceMap, sumSinceBaseline } from '../../dashboard/headlineStats.js';
import { useSeeFindings } from '../../dashboard/hooks/useSeeFindings.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';
import { TERMINAL_RUN_STATES } from '../../../vocab/runState.js';

/** The trend row for `runId` when it is a finished run; null otherwise. */
function finishedRow(trend, runId) {
  const row = (trend || []).find((r) => r.runId === runId);
  if (!row) return null;
  return !row.status || TERMINAL_RUN_STATES.has(row.status) ? row : null;
}

/**
 * @param {{project: string|null, selectedSource: string, runId: string|null, trend: Array,
 *   dimensionNames: string[], onNavigate?: Function}} args
 * @returns {{since: Object|null, selectedRun: Object|null, seeFindings: Function|undefined}}
 */
export function useHistorySinceBaseline({ project, selectedSource, runId, trend, dimensionNames, onNavigate }) {
  const api = useApi();
  const row = finishedRow(trend, runId);
  const enabled = Boolean(project && row) && selectedSource !== PROJECT_SOURCE.SHARED;
  const query = useQuery({
    queryKey: projectKeys.runDiff(project, runId),
    queryFn: () => api.getRunDiff(project, runId),
    enabled,
    staleTime: Infinity,
    retry: false,
  });
  const since = useMemo(() => {
    if (!enabled || !query.data) return null;
    return sumSinceBaseline(filterSinceBaseline(reduceDiffToSinceMap(query.data), dimensionNames));
  }, [enabled, query.data, dimensionNames]);
  const selectedRun = row ? { runId, dateLabel: row.dateLabel, commitSha: query.data?.commitSha ?? null } : null;
  const { seeFindings } = useSeeFindings({
    project, runId, dateLabel: row?.dateLabel, since, onNavigate, selectedSource, dimensionNames,
  });
  return { since, selectedRun, seeFindings };
}
