import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { sharedKeys } from '../../../api/queryKeys.js';
import { buildPublishedAtMap } from './publishOptimisticCache.js';

// The two react-query queries usePublish decorates local project cards with
// -- whether a shared repo is configured, and each project's publishedAt
// (only present on the SHARED list, git-log-derived -- see
// services/shared_repo.py's published_meta()). Extracted verbatim from
// usePublish.js; see that file's own doc comment for why these share cache
// keys with useSharedProjects and fetch with refresh:false.
export function usePublishQueries({ enabled, getSharedStatus, sharedListProjects }) {
  const statusQuery = useQuery({
    queryKey: sharedKeys.status(),
    queryFn: getSharedStatus,
    enabled,
  });

  const configured = !!statusQuery.data?.configured;

  const listQuery = useQuery({
    queryKey: sharedKeys.list(),
    queryFn: () => sharedListProjects({ refresh: false }),
    enabled: enabled && configured,
  });

  const publishedAtByProject = useMemo(
    () => buildPublishedAtMap(listQuery.data?.projects),
    [listQuery.data],
  );

  return { statusQuery, configured, listQuery, publishedAtByProject };
}
