import { useEffect } from 'react';

/**
 * useProjectState.js's warm-up poll: while the backend is still computing
 * summaries, refresh the list every few seconds so grades fill in as they
 * land. Stops on settle and on failure (the failure state has its own
 * retry/reconnect lanes). Extracted verbatim.
 */
export function useProjectWarmupPoll({ projects, projectsLoaded, projectsLoadFailed, loadProjects, summaryPollMs }) {
  const anySummaryPending = projects.some((p) => p.summaryPending);
  useEffect(() => {
    if (!anySummaryPending || !projectsLoaded || projectsLoadFailed) return undefined;
    const id = setInterval(() => { loadProjects(); }, summaryPollMs);
    return () => clearInterval(id);
  }, [anySummaryPending, projectsLoaded, projectsLoadFailed, loadProjects, summaryPollMs]);
}
