import { useState, useEffect, useCallback, useRef } from 'react';
import { useApi } from '../api/ApiContext.jsx';
import {
  DEFAULT_SOURCE, persistProject, persistSource, readStoredProject, readStoredSource, resolveInitialProject,
} from './projectStateStorage.js';
import { useProjectAutoRetry } from './useProjectAutoRetry.js';
import { useProjectWarmupPoll } from './useProjectWarmupPoll.js';

const DEFAULT_RUN = 'latest';
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY_MS = 400;
const DEFAULT_SUMMARY_POLL_MS = 3000;
const DEFAULT_AUTO_RETRY_MS = 30000;

// Resilient loader. A *transient* fetch failure (e.g. an aborted request
// during a startup/reload race) must NOT be mistaken for "no projects" —
// that used to strand the user in the onboarding wizard even though their
// projects were fine. Retry a few times; on genuine exhaustion return null
// so the caller skips onboarding, and raise projectsLoadFailed so the UI
// can offer a retry instead of spinning forever (retries used to exhaust
// silently, leaving a permanent LoadingScreen even after the backend
// recovered). A successful fetch that returns an empty array is still a
// real "fresh user" -> onboarding.
function makeLoadProjects({ listProjects, maxRetries, retryDelayMs, loadInFlightRef, setProjectsLoadFailed, setProjects, setProjectsLoaded }) {
  return function load(attempt = 0) {
    if (attempt === 0) {
      loadInFlightRef.current = true;
      setProjectsLoadFailed(false);
    }
    return listProjects()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.projects || []);
        setProjects(list);
        setProjectsLoaded(true);
        loadInFlightRef.current = false;
        return list;
      })
      .catch((err) => {
        if (attempt < maxRetries) {
          return new Promise((resolve) => setTimeout(resolve, retryDelayMs))
            .then(() => load(attempt + 1));
        }
        console.warn('Failed to load projects after retries:', err);
        setProjectsLoadFailed(true);
        loadInFlightRef.current = false;
        return null;
      });
  };
}

// Boot-time selection resolution against a freshly loaded list. A null list
// means the load failed after retries, and must NOT force onboarding.
function resolveSelectionFor(list, { selectedProject, selectedSource, handleProjectChange, onNoProjects, storage }) {
  if (!list) return;
  resolveInitialProject({
    list,
    currentProject: selectedProject,
    currentSource: selectedSource,
    onChangeProject: handleProjectChange,
    onNoProjects,
    storage,
  });
}

// Same load + selection resolution as the mount effect, for the failure-state
// Retry action (and the reconnect re-arm): a retry that succeeds must also
// migrate a stale stored selection, exactly like boot.
function makeRetryLoadProjects({ loadProjects, ...selection }) {
  return function retryLoadProjects() {
    return loadProjects().then((list) => {
      resolveSelectionFor(list, selection);
      return list;
    });
  };
}

function makeHandleProjectChange({ setSelectedProject, setSelectedSource, setSelectedRun, storage }) {
  return function handleProjectChange(name, source = DEFAULT_SOURCE) {
    persistProject(setSelectedProject, name, storage);
    persistSource(setSelectedSource, source, storage);
    setSelectedRun(DEFAULT_RUN);
  };
}

function makeSelectProjectAndRun({ setSelectedProject, setSelectedSource, setSelectedRun, storage }) {
  return function selectProjectAndRun(project, runId) {
    persistProject(setSelectedProject, project, storage);
    persistSource(setSelectedSource, DEFAULT_SOURCE, storage);
    setSelectedRun(runId || DEFAULT_RUN);
  };
}

// Groups the hook's own useState/useRef declarations so useProjectState's
// body stays under the function-length cap; still called unconditionally at
// the top of the outer hook, so hook-order rules are unaffected.
function useProjectStateFields(storage) {
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [projectsLoadFailed, setProjectsLoadFailed] = useState(false);
  const [selectedProject, setSelectedProject] = useState(() => readStoredProject(storage));
  const [selectedSource, setSelectedSource] = useState(() => readStoredSource(storage));
  const [selectedRun, setSelectedRun] = useState(DEFAULT_RUN);
  const loadInFlightRef = useRef(false);
  return {
    projects, setProjects, projectsLoaded, setProjectsLoaded, projectsLoadFailed, setProjectsLoadFailed,
    selectedProject, setSelectedProject, selectedSource, setSelectedSource,
    selectedRun, setSelectedRun, loadInFlightRef,
  };
}

function makeSelectionHandlers({ setSelectedProject, setSelectedSource, setSelectedRun, storage }) {
  const handleProjectChange = makeHandleProjectChange({ setSelectedProject, setSelectedSource, setSelectedRun, storage });
  const selectProjectAndRun = makeSelectProjectAndRun({ setSelectedProject, setSelectedSource, setSelectedRun, storage });
  function handleRunChange(runId) { setSelectedRun(runId); }
  return { handleProjectChange, selectProjectAndRun, handleRunChange };
}

// The project-list fetch: the retrying loader and the Retry action that also
// re-resolves the stored selection, like boot does.
function useProjectListLoader({ listProjects, maxRetries, retryDelayMs, fields, handleProjectChange, onNoProjects, storage }) {
  const { loadInFlightRef, setProjectsLoadFailed, setProjects, setProjectsLoaded, selectedProject, selectedSource } = fields;
  const loadProjects = useCallback(
    makeLoadProjects({ listProjects, maxRetries, retryDelayMs, loadInFlightRef, setProjectsLoadFailed, setProjects, setProjectsLoaded }),
    [listProjects, maxRetries, retryDelayMs],
  );
  const retryLoadProjects = makeRetryLoadProjects({ loadProjects, selectedProject, selectedSource, handleProjectChange, onNoProjects, storage });
  return { loadProjects, retryLoadProjects };
}

// The failure screen owns its own recovery: while it shows, retry quietly in
// the background (hooks/useProjectAutoRetry.js); and the warm-up poll
// (hooks/useProjectWarmupPoll.js).
function useProjectBackgroundRefresh({ fields, listProjects, handleProjectChange, onNoProjects, storage, autoRetryMs, loadProjects, summaryPollMs }) {
  const {
    projects, projectsLoaded, projectsLoadFailed, loadInFlightRef, setProjects,
    setProjectsLoaded, setProjectsLoadFailed, selectedProject, selectedSource,
  } = fields;
  useProjectAutoRetry({
    projectsLoadFailed, projectsLoaded, loadInFlightRef, listProjects, setProjects,
    setProjectsLoaded, setProjectsLoadFailed, selectedProject, selectedSource, handleProjectChange, onNoProjects, storage, autoRetryMs,
  });
  useProjectWarmupPoll({ projects, projectsLoaded, projectsLoadFailed, loadProjects, summaryPollMs });
}

function useInitialProjectLoad({ loadProjects, ...selection }) {
  useEffect(() => {
    loadProjects().then((list) => {
      resolveSelectionFor(list, selection);
    }).catch((err) => {
      // loadProjects already retries and never rejects; defense in depth.
      console.warn('[useProjectState] initial project load failed unexpectedly:', err);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- initial load runs once on mount; later loads go through the retry and warm-up hooks
}

/**
 * Manages the selected project, run, and project list state.
 *
 * @param {Object} params
 * @param {Function} [params.onNoProjects] - Callback invoked when the loaded project list is empty
 *   (e.g. to redirect to the evaluate tab).
 * @param {Storage} [params.storage=localStorage] - Storage used to persist the selected project/source.
 * @param {number} [params.maxRetries=3] - Retries for a failed project-list fetch before giving up
 *   and setting projectsLoadFailed.
 * @param {number} [params.retryDelayMs=400] - Delay between those retries, in milliseconds.
 * @param {number} [params.summaryPollMs=3000] - Poll interval while any project's summary is pending.
 * @param {number} [params.autoRetryMs=30000] - Interval for the background auto-retry that runs while
 *   projectsLoadFailed is true.
 * @returns {{ projects: Array, projectsLoaded: boolean, projectsLoadFailed: boolean,
 *   retryLoadProjects: Function, setProjects: Function, selectedProject: string, selectedSource: string,
 *   selectedRun: string, setSelectedRun: Function, loadProjects: Function, handleProjectChange: Function,
 *   handleRunChange: Function, selectProjectAndRun: Function }}
 */
export function useProjectState({
  onNoProjects,
  storage = localStorage,
  maxRetries = DEFAULT_MAX_RETRIES,
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  summaryPollMs = DEFAULT_SUMMARY_POLL_MS,
  autoRetryMs = DEFAULT_AUTO_RETRY_MS,
}) {
  const { listProjects } = useApi();
  const fields = useProjectStateFields(storage);
  const {
    projects, setProjects, projectsLoaded, projectsLoadFailed,
    selectedProject, setSelectedProject, selectedSource, setSelectedSource, selectedRun, setSelectedRun,
  } = fields;

  const { handleProjectChange, selectProjectAndRun, handleRunChange } =
    makeSelectionHandlers({ setSelectedProject, setSelectedSource, setSelectedRun, storage });

  const { loadProjects, retryLoadProjects } = useProjectListLoader({
    listProjects, maxRetries, retryDelayMs, fields, handleProjectChange, onNoProjects, storage,
  });

  useProjectBackgroundRefresh({ fields, listProjects, handleProjectChange, onNoProjects, storage, autoRetryMs, loadProjects, summaryPollMs });

  useInitialProjectLoad({ loadProjects, selectedProject, selectedSource, handleProjectChange, onNoProjects, storage });

  return {
    projects, projectsLoaded, projectsLoadFailed, retryLoadProjects, setProjects,
    selectedProject, selectedSource, selectedRun, setSelectedRun, loadProjects,
    handleProjectChange, handleRunChange, selectProjectAndRun,
  };
}
