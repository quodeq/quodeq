import { useCallback } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { standardsKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { useStandardsQuery } from './useStandardsQuery.js';

/**
 * Manages per-project standards threshold overrides.
 *
 * @param {string|null|undefined} projectId
 * @returns {{ overrides: Object, counts: Object, loading: boolean, error: string|null, save: (nextOverrides: Object) => Promise<void>, preview: (nextOverrides: Object) => Promise<{overrides: Object, changedDimensions: string[]}> }}
 */
export function useStandardsOverrides(projectId) {
  const { getStandardsOverrides, putStandardsOverrides } = useApi();
  const { data, isLoading, error, setMutationError, queryClient } = useStandardsQuery({
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
        setMutationError(apiErrorMessage(err, 'standards.saveOverridesFailed'));
        throw err;
      }
    },
    [projectId, putStandardsOverrides, queryClient],
  );

  const preview = useCallback(
    (nextOverrides) => putStandardsOverrides(projectId, nextOverrides, { dryRun: true }),
    [projectId, putStandardsOverrides],
  );

  return {
    overrides: data?.overrides ?? {},
    counts: data?.counts ?? {},
    loading: isLoading,
    error,
    save,
    preview,
  };
}
