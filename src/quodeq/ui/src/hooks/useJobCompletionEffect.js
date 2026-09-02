import { useEffect, useRef } from 'react';
import { projectKeys } from '../api/queryKeys.js';

/**
 * useEvaluationLifecycle.js's job-completion effect: on-start nav, the
 * project-list refresh, and the scores/compare-summary cache invalidation.
 * Extracted verbatim -- invalidation keys unchanged.
 */
export function useJobCompletionEffect({ job, navTab, loadProjects, setProjects, queryClient, selectedProject, selectProjectAndRun }) {
  const prevJobRef = useRef(null);
  const refreshedRunRef = useRef(null);
  useEffect(() => {
    if (job?.status === 'running' && !prevJobRef.current) navTab('evaluate');
    // Auto-refresh dashboard data as soon as the run completes
    const finished = job && job.status !== 'running' && job.outputProject && job.outputRunId;
    if (finished && refreshedRunRef.current !== job.outputRunId) {
      refreshedRunRef.current = job.outputRunId;
      loadProjects()
        .then((list) => setProjects(list))
        .catch((err) => console.error('Failed to refresh projects:', err));
      // useAppState's dashboard-key effect (removed as redundant: the
      // selectProjectAndRun call below mints a new dashboard query key on its
      // own) only ever covered the dashboard side. The scores side has its
      // own key -- projectKeys.scores(project, null, source), the `latest`
      // query in useProjectScores -- and it does NOT change when selectedRun
      // flips, because `asOf` only resolves to the new run once
      // `availableRuns` (itself sourced from this same query) already lists
      // it. Left un-invalidated, a user parked on the Overview when a run
      // completes never gets the refreshed `availableRuns`/`accumulated`:
      // repeat-run projects show stale grades until a tab round-trip, and a
      // first-run project never gets `accumulated`, so `contentReady` stays
      // false and the page sits on the inline loader indefinitely. Evaluations
      // only ever write to the
      // local repo, so the 'local' source (the default) is always correct
      // here regardless of which source tab the user has open elsewhere.
      // Unconditional on outputProject: invalidating an inactive observer's
      // query just marks it stale (no fetch), so this is a harmless no-op
      // when nobody is looking at that project.
      queryClient.invalidateQueries({ queryKey: projectKeys.scores(job.outputProject, null, 'local') });
      // The Compare tab holds one slim summary per project; without this a
      // finished run on ANY project leaves its fleet row stale until the
      // staleTime expires or the tab remounts. Same harmless-no-op rule as
      // above when Compare isn't mounted.
      queryClient.invalidateQueries({ queryKey: projectKeys.compareSummary(job.outputProject, 'local') });
      // Only move the selection to the finished run when the user is
      // already on that project (or has none selected, e.g. first-eval
      // onboarding). Unconditional switching yanked a user browsing
      // project B into project A the moment A's background run finished,
      // without any nav reset. The evaluate card's "view results" button
      // remains the explicit way to jump to another project's results.
      if (!selectedProject || job.outputProject === selectedProject) {
        selectProjectAndRun(job.outputProject, job.outputRunId);
      }
    }
    prevJobRef.current = job;
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps
}
