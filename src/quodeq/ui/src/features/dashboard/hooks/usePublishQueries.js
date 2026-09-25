import { useMemo } from 'react';
import { useSharedStatusAndList } from './useSharedStatusAndList.js';
import { buildPublishedAtMap } from './publishOptimisticCache.js';

/**
 * The two react-query queries usePublish decorates local project cards with
 * -- whether a shared repo is configured, and each project's publishedAt
 * (only present on the SHARED list, git-log-derived -- see
 * services/shared_repo.py's published_meta()). See usePublish.js's doc
 * comment for why these share cache keys with useSharedProjects and fetch
 * with refresh:false.
 */
export function usePublishQueries({ enabled, getSharedStatus, sharedListProjects }) {
  const { statusQuery, configured, listQuery } = useSharedStatusAndList({ getSharedStatus, sharedListProjects, enabled });

  const publishedAtByProject = useMemo(
    () => buildPublishedAtMap(listQuery.data?.projects),
    [listQuery.data],
  );

  return { statusQuery, configured, listQuery, publishedAtByProject };
}
