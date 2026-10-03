import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys } from '../../../api/queryKeys.js';
import { STAGE_STATUS } from '../../../vocab/stageStatus.js';

export const STAGE_DEBOUNCE_MS = 250;

/**
 * The scoring stages of one dimension's principles: `stored` with the saved
 * formula parameters (one GET, cached for the session) and `live` with the
 * editor's draft (one POST, 250 ms after the last draft change). A draft the
 * server rejects, or a request that fails, is logged and clears `live`, so
 * the stage falls back to the stored payload instead of a stale draft.
 * @param {object} args
 * @param {string|null} args.project
 * @param {string|null} args.runId
 * @param {string|null} args.dimension
 * @param {object|null} args.draft - the draft formula parameters (camelCase).
 * @param {boolean} args.enabled - false: nothing is requested.
 * @returns {{stored: object|null, live: object|null, principles: Array, status: string}}
 *   `status` is `error` when the stored stages could not be read.
 */
export function useStageExplain({ project, runId, dimension, draft, enabled }) {
  const api = useApi();
  const active = Boolean(enabled && project && runId && dimension);
  const query = useQuery({
    queryKey: projectKeys.gradeExplain(project, runId, dimension),
    queryFn: () => api.getGradeExplain(project, runId, dimension),
    enabled: active,
    staleTime: Infinity,
    retry: false,
  });
  const stored = query.data || null;

  const [live, setLive] = useState(null);
  const timerRef = useRef(null);
  const requestRef = useRef(0);
  // Another run or dimension: the draft stages of the old one are gone, and a
  // response still in flight for it must not land. Declared before the
  // request effect so a request scheduled in the same commit gets a newer ticket.
  useEffect(() => {
    requestRef.current += 1;
    setLive(null);
  }, [project, runId, dimension]);
  useEffect(() => {
    if (!active || !stored || !draft) return undefined;
    clearTimeout(timerRef.current);
    const ticket = ++requestRef.current;
    timerRef.current = setTimeout(() => {
      api.previewGradeExplain(project, runId, dimension, draft)
        .then((payload) => { if (ticket === requestRef.current) setLive(payload); })
        .catch((err) => {
          // A superseded ticket is cancelled work, not a failure.
          if (ticket !== requestRef.current) return;
          console.warn('[grade-formula] stage preview failed:', err);
          setLive(null);
        });
    }, STAGE_DEBOUNCE_MS);
    return () => clearTimeout(timerRef.current);
  }, [active, stored, draft, project, runId, dimension, api]);

  return {
    stored,
    live,
    // The picker lists the run's principles: the stored payload's, never a
    // draft response that may belong to an earlier selection.
    principles: stored?.principles || [],
    status: stageStatus(active, query),
  };
}

function stageStatus(active, query) {
  if (!active) return STAGE_STATUS.UNAVAILABLE;
  if (query.isError) return STAGE_STATUS.ERROR;
  if (query.isPending) return STAGE_STATUS.LOADING;
  return query.data ? STAGE_STATUS.READY : STAGE_STATUS.IDLE;
}
