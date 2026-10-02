import { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../api/ApiContext.jsx';
import { projectsKeys } from '../api/queryKeys.js';
import { invalidateProjects } from './invalidateProjects.js';
import {
  DEFAULT_SOURCE, persistProject, persistSource, readStoredProject, readStoredSource, resolveInitialProject,
} from './projectStateStorage.js';
import { LATEST_RUN_ID } from '../constants.js';
import { backoffDelay } from '../utils/backoff.js';

// Stable empty list for the not-yet-loaded state, so consumers' memo deps do
// not churn on every render before the first load lands.
const NO_PROJECTS = [];
const DEFAULT_RETRY_DELAY_MS = 400;
const DEFAULT_SUMMARY_POLL_MS = 3000;
const DEFAULT_AUTO_RETRY_MS = 30000;
// Ceiling for the jittered backoff between project-list retries (see
// backoffDelay): keeps a large maxRetries from growing the wait unbounded.
const RETRY_DELAY_CAP_MS = 5000;
// How long a fetched list counts as fresh: mutations invalidate it
// explicitly, so this only dedupes mounts that ask for it at the same time.
const PROJECTS_STALE_MS = 5000;

// The poll cadence of the project-list query. While the list is in a failed
// state it retries quietly in the background, so a recovered backend clears
// the failure screen without the user clicking Retry; while any summary is
// still being computed it refreshes every few seconds so grades fill in as
// they land; otherwise it does not poll.
function projectsRefetchInterval(query, { summaryPollMs, autoRetryMs }) {
  if (query.state.error) return autoRetryMs;
  return query.state.data?.some((p) => p.summaryPending) ? summaryPollMs : false;
}

// Retries back off with jitter. The retry count falls back to the
// QueryClient's default unless the caller pins one.
function projectsRetryOptions(maxRetries, retryDelayMs) {
  const retryDelay = (attempt) => backoffDelay(attempt, retryDelayMs, RETRY_DELAY_CAP_MS);
  return maxRetries === undefined ? { retryDelay } : { retry: maxRetries, retryDelay };
}

/**
 * The local project list as a shared query. Every mutation that changes the
 * project set invalidates projectsKeys.list() (hooks/invalidateProjects.js),
 * so the list is never a private copy some component has to remember to
 * reload.
 */
function useProjectsQuery({ listProjects, maxRetries, retryDelayMs, summaryPollMs, autoRetryMs }) {
  return useQuery({
    queryKey: projectsKeys.list(),
    queryFn: async () => {
      const data = await listProjects();
      return Array.isArray(data) ? data : (data?.projects ?? []);
    },
    staleTime: PROJECTS_STALE_MS,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => projectsRefetchInterval(query, { summaryPollMs, autoRetryMs }),
    ...projectsRetryOptions(maxRetries, retryDelayMs),
  });
}

// Boot-time selection resolution against the first list that loaded.
function resolveSelectionFor(list, { selectedProject, selectedSource, handleProjectChange, onNoProjects, storage }) {
  resolveInitialProject({
    list,
    currentProject: selectedProject,
    currentSource: selectedSource,
    onChangeProject: handleProjectChange,
    onNoProjects,
    storage,
  });
}

function makeHandleProjectChange({ setSelectedProject, setSelectedSource, setSelectedRun, storage }) {
  return function handleProjectChange(name, source = DEFAULT_SOURCE) {
    persistProject(setSelectedProject, name, storage);
    persistSource(setSelectedSource, source, storage);
    setSelectedRun(LATEST_RUN_ID);
  };
}

function makeSelectProjectAndRun({ setSelectedProject, setSelectedSource, setSelectedRun, storage }) {
  return function selectProjectAndRun(project, runId) {
    persistProject(setSelectedProject, project, storage);
    persistSource(setSelectedSource, DEFAULT_SOURCE, storage);
    setSelectedRun(runId || LATEST_RUN_ID);
  };
}

// Groups the hook's own selection state so useProjectState's body stays under
// the function-length cap; still called unconditionally at the top of the
// outer hook, so hook-order rules are unaffected.
function useSelectionFields(storage) {
  const [selectedProject, setSelectedProject] = useState(() => readStoredProject(storage));
  const [selectedSource, setSelectedSource] = useState(() => readStoredSource(storage));
  const [selectedRun, setSelectedRun] = useState(LATEST_RUN_ID);
  return { selectedProject, setSelectedProject, selectedSource, setSelectedSource, selectedRun, setSelectedRun };
}

function makeSelectionHandlers({ setSelectedProject, setSelectedSource, setSelectedRun, storage }) {
  const handleProjectChange = makeHandleProjectChange({ setSelectedProject, setSelectedSource, setSelectedRun, storage });
  const selectProjectAndRun = makeSelectProjectAndRun({ setSelectedProject, setSelectedSource, setSelectedRun, storage });
  function handleRunChange(runId) { setSelectedRun(runId); }
  return { handleProjectChange, selectProjectAndRun, handleRunChange };
}

// Boot-time selection resolution runs once, against the first list that
// actually loaded: a failed load has no data, so it never forces onboarding,
// and a Retry or background retry that succeeds resolves exactly like boot.
// Later refetches leave the selection alone; the mutation that changed the
// list owns any selection move (delete, job completion).
function useResolveSelectionOnFirstLoad(list, selection) {
  const resolvedRef = useRef(false);
  useEffect(() => {
    if (resolvedRef.current || list === undefined) return;
    resolvedRef.current = true;
    resolveSelectionFor(list, selection);
  }, [list]); // eslint-disable-line react-hooks/exhaustive-deps -- resolves once, with the selection current at first load
}

// The list's imperative handles, all routed through the query cache so every
// holder of the list sees the same data.
function useProjectListHandles(queryClient, query) {
  const loadProjects = useCallback(
    () => invalidateProjects(queryClient).then(() => queryClient.getQueryData(projectsKeys.list()) ?? []),
    [queryClient],
  );
  const setProjects = useCallback((list) => queryClient.setQueryData(projectsKeys.list(), list), [queryClient]);
  return { loadProjects, setProjects, retryLoadProjects: query.refetch };
}

/**
 * Manages the selected project, run, and the local project list (a shared
 * react-query query, see useProjectsQuery).
 *
 * @param {Object} [params]
 * @param {Function} [params.onNoProjects] - Callback invoked when the first loaded project list is empty.
 * @param {Storage} [params.storage=localStorage] - Storage used to persist the selected project/source.
 * @param {number} [params.maxRetries] - Retries for a failed project-list fetch before giving up
 *   and setting projectsLoadFailed; defaults to the QueryClient's retry setting.
 * @param {number} [params.retryDelayMs=400] - Base of the jittered backoff between those retries, in milliseconds.
 * @param {number} [params.summaryPollMs=3000] - Poll interval while any project's summary is pending.
 * @param {number} [params.autoRetryMs=30000] - Interval for the background retry that runs while
 *   the list is in a failed state.
 * @returns {{ projects: Array, projectsLoaded: boolean, projectsLoadFailed: boolean,
 *   retryLoadProjects: Function, setProjects: Function, selectedProject: string, selectedSource: string,
 *   selectedRun: string, setSelectedRun: Function, loadProjects: Function, handleProjectChange: Function,
 *   handleRunChange: Function, selectProjectAndRun: Function }}
 */
export function useProjectState({
  onNoProjects,
  storage = localStorage,
  maxRetries,
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  summaryPollMs = DEFAULT_SUMMARY_POLL_MS,
  autoRetryMs = DEFAULT_AUTO_RETRY_MS,
} = {}) {
  const { listProjects } = useApi();
  const queryClient = useQueryClient();
  const query = useProjectsQuery({ listProjects, maxRetries, retryDelayMs, summaryPollMs, autoRetryMs });
  const {
    selectedProject, setSelectedProject, selectedSource, setSelectedSource, selectedRun, setSelectedRun,
  } = useSelectionFields(storage);

  const { handleProjectChange, selectProjectAndRun, handleRunChange } =
    makeSelectionHandlers({ setSelectedProject, setSelectedSource, setSelectedRun, storage });

  useResolveSelectionOnFirstLoad(query.data, { selectedProject, selectedSource, handleProjectChange, onNoProjects, storage });
  const { loadProjects, setProjects, retryLoadProjects } = useProjectListHandles(queryClient, query);

  // A refetch that fails after a good load keeps the last list (react-query
  // keeps data on error), so "loaded" means "we have a list". A failed FIRST
  // load stays unloaded: nothing downstream may read it as "no projects" and
  // fall into onboarding or the empty landing.
  return {
    projects: query.data ?? NO_PROJECTS,
    projectsLoaded: query.data !== undefined,
    projectsLoadFailed: query.isError,
    retryLoadProjects, setProjects,
    selectedProject, selectedSource, selectedRun, setSelectedRun, loadProjects,
    handleProjectChange, handleRunChange, selectProjectAndRun,
  };
}
