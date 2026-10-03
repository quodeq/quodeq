import { useCallback, useEffect, useRef, useState } from 'react';
import { refreshProject } from '../../../api/projects.js';
import { queryClient } from '../../../api/queryClient.js';
import { projectKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { pluralKey } from '../../../utils/plural.js';
import { REFRESH_OUTCOME } from '../../../vocab/refreshOutcome.js';

// A refusal's error `code` (a REFRESH_OUTCOME name) -> its translated copy.
const ERROR_KEYS = {
  BUSY: 'projects.refreshErrorBusy',
  DIRTY: 'projects.refreshErrorDirty',
  NO_UPSTREAM: 'projects.refreshErrorNoUpstream',
  DIVERGED: 'projects.refreshErrorDiverged',
  FETCH_FAILED: 'projects.refreshErrorFetchFailed',
  NOT_REFRESHABLE: 'projects.refreshErrorNotRefreshable',
};

function successNote({ outcome, newCommits }) {
  if (outcome === REFRESH_OUTCOME.UP_TO_DATE) return t('projects.refreshUpToDate');
  if (!newCommits) return t('projects.refreshUpdated');
  return t(pluralKey(newCommits, 'projects.refreshUpdatedOne', 'projects.refreshUpdatedMany'), { count: newCommits });
}

/**
 * One project card's "fetch latest code" action.
 *
 * `note` is the last success sentence and `error` the last refusal (with
 * git's own output tail as `errorDetail`); a new run clears both.
 */
export function useProjectRefresh(projectId) {
  const [state, setState] = useState({ pending: false, note: null, error: null, errorDetail: null });
  const pendingRef = useRef(false);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const refresh = useCallback(async () => {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setState({ pending: true, note: null, error: null, errorDetail: null });
    let next;
    try {
      const result = await refreshProject(projectId);
      next = { pending: false, note: successNote(result), error: null, errorDetail: null };
      queryClient.invalidateQueries({ queryKey: projectKeys.info(projectId) });
    } catch (e) {
      const key = ERROR_KEYS[e?.code];
      next = {
        pending: false, note: null,
        error: key ? t(key) : (e?.message || t('projects.refreshErrorGeneric')),
        errorDetail: e?.body?.detail || null,
      };
    }
    pendingRef.current = false;
    if (mountedRef.current) setState(next);
  }, [projectId]);

  return { ...state, refresh };
}
