import { useCallback, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { standardsKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { STANDARDS_CHANGED_REASON, notifyStandardsChanged } from '../../../constants.js';

export const STANDARD_TYPES = { BUILTIN: 'builtin', QUODEQ: 'quodeq', COMMUNITY: 'community', CUSTOM: 'custom' };

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
  };
  for (const s of standards) {
    if (g[s.type]) g[s.type].push(s);
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
  const queryClient = useQueryClient();
  const [mutationError, setMutationError] = useState(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: standardsKeys.list(),
    queryFn: () => listStandards(),
  });

  const standards = data || [];

  const refresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: standardsKeys.list() });
    // The Evaluate picker keeps its own merged plugin+standards list outside
    // React Query; tell it the set of standards may have changed.
    notifyStandardsChanged(STANDARDS_CHANGED_REASON.LIST);
    return refetch();
  }, [queryClient, refetch]);

  const handleDelete = useCallback(
    makeHandleDelete({ deleteStandard, setMutationError, refresh }),
    [deleteStandard, refresh],
  );

  const handleDuplicate = useCallback(
    makeHandleDuplicate({ duplicateStandard, setMutationError, refresh, onDuplicated }),
    [duplicateStandard, refresh, onDuplicated],
  );

  const grouped = useMemo(() => groupStandards(standards), [standards]);

  const combinedError = mutationError || (error ? error.message : null);

  return {
    standards,
    grouped,
    loading: isLoading,
    error: combinedError,
    refresh,
    handleDelete,
    handleDuplicate,
  };
}
