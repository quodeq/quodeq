import { useCallback, useMemo } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { standardsKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { STANDARDS_CHANGED_REASON, notifyStandardsChanged } from '../../../constants.js';
import { useStandardsQuery } from './useStandardsQuery.js';

export const STANDARD_TYPES = { BUILTIN: 'builtin', QUODEQ: 'quodeq', COMMUNITY: 'community', CUSTOM: 'custom' };

// Fallback bucket for a standard whose `type` doesn't match any known
// STANDARD_TYPES value. Keeps it visible (StandardsTable folds this bucket
// into its flat row list) instead of silently dropping it from the list.
export const UNKNOWN_STANDARD_TYPE = 'unknown';

function makeHandleDelete({ deleteStandard, setMutationError, refresh }) {
  return async (id) => {
    try {
      await deleteStandard(id);
      setMutationError(null);
      await refresh();
      return true;
    } catch (err) {
      setMutationError(apiErrorMessage(err, 'standards.deleteFailed'));
      return false;
    }
  };
}

function makeHandleDuplicate({ duplicateStandard, setMutationError, refresh, onDuplicated }) {
  return async (id, newId) => {
    try {
      await duplicateStandard(id, newId);
      setMutationError(null);
      // Only after the server accepted it: the page marks the copy visible
      // for the current project, and an unknown id would fail that PUT.
      if (onDuplicated) onDuplicated(newId);
      await refresh();
    } catch (err) {
      setMutationError(apiErrorMessage(err, 'standards.duplicateFailed'));
    }
  };
}

function groupStandards(standards) {
  const g = {
    [STANDARD_TYPES.BUILTIN]: [],
    [STANDARD_TYPES.QUODEQ]: [],
    [STANDARD_TYPES.COMMUNITY]: [],
    [STANDARD_TYPES.CUSTOM]: [],
    [UNKNOWN_STANDARD_TYPE]: [],
  };
  for (const s of standards) {
    if (g[s.type]) {
      g[s.type].push(s);
    } else {
      // Unrecognized type: keep the standard visible in its own bucket
      // instead of dropping it from the list.
      console.warn('[useStandards] unrecognized standard type:', s.type);
      g[UNKNOWN_STANDARD_TYPE].push(s);
    }
  }
  return g;
}

/**
 * The standards list, grouped by type, with delete and duplicate.
 *
 * A refresh also notifies the Evaluate picker, which keeps its own merged
 * plugin+standards list outside React Query and would otherwise go stale.
 * `error` carries whichever failed last, the listing or a mutation.
 */
export function useStandards({ onDuplicated } = {}) {
  const { listStandards, deleteStandard, duplicateStandard } = useApi();
  const { data, isLoading, error, setMutationError, queryClient } = useStandardsQuery({
    queryKey: standardsKeys.list(),
    queryFn: () => listStandards(),
  });

  const standards = data || [];

  // invalidateQueries already refetches the mounted list query and its
  // promise settles when that fetch does; a second refetch() would cancel
  // it and fetch again.
  const refresh = useCallback(() => {
    // The Evaluate picker keeps its own merged plugin+standards list outside
    // React Query; tell it the set of standards may have changed.
    notifyStandardsChanged(STANDARDS_CHANGED_REASON.LIST);
    return queryClient.invalidateQueries({ queryKey: standardsKeys.list() });
  }, [queryClient]);

  const handleDelete = useCallback(
    makeHandleDelete({ deleteStandard, setMutationError, refresh }),
    [deleteStandard, refresh],
  );

  const handleDuplicate = useCallback(
    makeHandleDuplicate({ duplicateStandard, setMutationError, refresh, onDuplicated }),
    [duplicateStandard, refresh, onDuplicated],
  );

  const grouped = useMemo(() => groupStandards(standards), [standards]);

  return {
    standards,
    grouped,
    loading: isLoading,
    error,
    refresh,
    handleDelete,
    handleDuplicate,
  };
}
