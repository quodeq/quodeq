import { useMemo } from 'react';
import { useByTypeData } from '../../violations/hooks/useByTypeData.js';
import { typesRows } from '../stages/typesRows.js';

/**
 * The TYPES tab's data: the run's dimensions with their findings, the run
 * diff for the baseline counts, the standards for the text, and the draft
 * formula for the weights.
 * @param {{project: string|null, runId: string|null, dimensions: Array, selectedSource?: string, draft: object|null}} args
 *   `dimensions` are the dashboard's run dimensions (each with `violations`).
 * @returns {{rows: Array, loading: boolean}}
 */
export function useTypesRows({ project, runId, dimensions, selectedSource, draft }) {
  const runDims = useMemo(
    () => (runId ? (dimensions || []).map((d) => ({ ...d, fromRunId: runId })) : []),
    [dimensions, runId],
  );
  const { diffsByRun, standardsByDim, loading } = useByTypeData({
    project, dimensions: runDims, selectedSource, enabled: Boolean(project && runId),
  });
  const rows = useMemo(
    () => typesRows({ dimensions: runDims, diffsByRun, standardsByDim, draft }),
    [runDims, diffsByRun, standardsByDim, draft],
  );
  return { rows, loading };
}
