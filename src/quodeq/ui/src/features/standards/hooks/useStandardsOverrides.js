import { useCallback, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { standardsKeys } from '../../../api/queryKeys.js';

/**
 * Manages per-project standards threshold overrides.
 *
 * @param {string|null|undefined} projectId
 * @returns {{ overrides: Object, counts: Object, loading: boolean, error: string|null, save: (nextOverrides: Object) => Promise<void> }}
 */
export function useStandardsOverrides(projectId) {
  const { getStandardsOverrides, putStandardsOverrides } = useApi();
  const queryClient = useQueryClient();
  const [mutationError, setMutationError] = useState(null);

  const { data, isLoading, error } = useQuery({
    queryKey: standardsKeys.overrides(projectId),
    queryFn: () => getStandardsOverrides(projectId),
    enabled: Boolean(projectId),
  });

  const save = useCallback(
    async (nextOverrides) => {
      try {
        await putStandardsOverrides(projectId, nextOverrides);
        setMutationError(null);
        await queryClient.invalidateQueries({ queryKey: standardsKeys.overrides(projectId) });
      } catch (err) {
        setMutationError(err.message || 'Failed to save overrides');
        throw err;
      }
    },
    [projectId, putStandardsOverrides, queryClient],
  );

  return {
    overrides: data?.overrides ?? {},
    counts: data?.counts ?? {},
    loading: isLoading,
    error: mutationError || (error ? error.message : null),
    save,
  };
}
