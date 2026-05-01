import { useCallback, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { standardsKeys } from '../../../api/queryKeys.js';

export const STANDARD_TYPES = { BUILTIN: 'builtin', QUODEQ: 'quodeq', COMMUNITY: 'community', CUSTOM: 'custom' };

export function useStandards() {
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
    return refetch();
  }, [queryClient, refetch]);

  const handleDelete = useCallback(async (id) => {
    try {
      await deleteStandard(id);
      setMutationError(null);
      await refresh();
    } catch (err) {
      setMutationError(err.message || 'Failed to delete standard');
    }
  }, [deleteStandard, refresh]);

  const handleDuplicate = useCallback(async (id, newId) => {
    try {
      await duplicateStandard(id, newId);
      setMutationError(null);
      await refresh();
    } catch (err) {
      setMutationError(err.message || 'Failed to duplicate standard');
    }
  }, [duplicateStandard, refresh]);

  const grouped = useMemo(() => {
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
  }, [standards]);

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
