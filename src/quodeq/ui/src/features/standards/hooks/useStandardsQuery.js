import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

/**
 * A Standards query plus the error of the last mutation made against it.
 *
 * `error` is the mutation error when one is set, else the failed query's
 * message, else null. Mutations report through `setMutationError` and
 * refresh through `queryClient`.
 *
 * @param {object} queryOptions - passed to useQuery as is
 * @returns {{ data: unknown, isLoading: boolean, error: string|null, setMutationError: Function, queryClient: object }}
 */
export function useStandardsQuery(queryOptions) {
  const queryClient = useQueryClient();
  const [mutationError, setMutationError] = useState(null);
  const { data, isLoading, error } = useQuery(queryOptions);
  return {
    data,
    isLoading,
    error: mutationError || (error ? error.message : null),
    setMutationError,
    queryClient,
  };
}
