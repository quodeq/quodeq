import { useEffect, useRef } from 'react';
import { projectKeys } from '../api/queryKeys.js';
import { invalidateProjects } from './invalidateProjects.js';
import { JOB_SOURCE, JOB_STATUS } from '../vocab/jobStatus.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';
import { NAV_TAB } from '../vocab/navTab.js';

/**
 * The evaluation job-completion effect: on-start nav, then, once per
 * finished run, the project-list refetch, the scores/compare-summary cache
 * invalidation, and the selection move to the new run.
 */
export function useJobCompletionEffect({ job, navTab, queryClient, selectedProject, selectProjectAndRun }) {
  const prevJobRef = useRef(null);
  const refreshedRunRef = useRef(null);
  useEffect(() => {
    // A run the app did not start (CI, terminal) is adopted in the
    // background: it never moves the user to another tab.
    const external = job?.source === JOB_SOURCE.EXTERNAL;
    if (job?.status === JOB_STATUS.RUNNING && !prevJobRef.current && !external) navTab(NAV_TAB.EVALUATE);
    // Auto-refresh dashboard data as soon as the run completes
    const finished = job && job.status !== JOB_STATUS.RUNNING && job.outputProject && job.outputRunId;
    if (finished && refreshedRunRef.current !== job.outputRunId) {
      refreshedRunRef.current = job.outputRunId;
      invalidateProjects(queryClient)
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
      queryClient.invalidateQueries({ queryKey: projectKeys.scores(job.outputProject, null, PROJECT_SOURCE.LOCAL) });
      // The Compare tab holds one slim summary per project; without this a
      // finished run on ANY project leaves its fleet row stale until the
      // staleTime expires or the tab remounts. Same harmless-no-op rule as
      // above when Compare isn't mounted.
      queryClient.invalidateQueries({ queryKey: projectKeys.compareSummary(job.outputProject, PROJECT_SOURCE.LOCAL) });
      // Only move the selection to the finished run when the user is
      // already on that project (or has none selected, e.g. first-eval
      // onboarding). Unconditional switching yanked a user browsing
      // project B into project A the moment A's background run finished,
      // without any nav reset. The evaluate card's "view results" button
      // remains the explicit way to jump to another project's results.
      // An external run never fills an empty selection either: a PR
      // review's project is a throwaway, and a nightly finishing at night
      // must not change what the user was looking at.
      const ownsSelection = external ? job.outputProject === selectedProject : (!selectedProject || job.outputProject === selectedProject);
      if (ownsSelection) selectProjectAndRun(job.outputProject, job.outputRunId);
    }
    prevJobRef.current = job;
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps
}
