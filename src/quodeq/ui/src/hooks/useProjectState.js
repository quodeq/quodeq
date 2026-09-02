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

/**
 * Manages the selected project, run, and project list state.
 *
 * @param {Object} params
 * @param {Function} [params.onNoProjects] - Callback invoked when the loaded project list is empty
 *   (e.g. to redirect to the evaluate tab).
 * @param {number} [params.summaryPollMs] - Poll interval while any project's summary is pending.
 * @returns {{ projects: Array, warmup: Object|null, setProjects: Function, selectedProject: string,
 *   selectedSource: string, selectedRun: string, setSelectedRun: Function, loadProjects: Function,
 *   handleProjectChange: Function, handleRunChange: Function, selectProjectAndRun: Function }}
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
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [projectsLoadFailed, setProjectsLoadFailed] = useState(false);
  const [warmup, setWarmup] = useState(null);
  const [selectedProject, setSelectedProject] = useState(() => readStoredProject(storage));
  const [selectedSource, setSelectedSource] = useState(() => readStoredSource(storage));
  const [selectedRun, setSelectedRun] = useState(DEFAULT_RUN);

  // Resilient loader. A *transient* fetch failure (e.g. an aborted request
  // during a startup/reload race) must NOT be mistaken for "no projects" —
  // that used to strand the user in the onboarding wizard even though their
  // projects were fine. Retry a few times; on genuine exhaustion return null
  // so the caller skips onboarding, and raise projectsLoadFailed so the UI
  // can offer a retry instead of spinning forever (retries used to exhaust
  // silently, leaving a permanent LoadingScreen even after the backend
  // recovered). A successful fetch that returns an empty array is still a
  // real "fresh user" -> onboarding.
  const loadInFlightRef = useRef(false);

  const loadProjects = useCallback(function load(attempt = 0) {
    if (attempt === 0) {
      loadInFlightRef.current = true;
      setProjectsLoadFailed(false);
    }
    return listProjects()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data?.projects || []);
        if (data && !Array.isArray(data)) setWarmup(data.warmup ?? null);
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
  }, [listProjects, maxRetries, retryDelayMs]);

  // Same load + boot-time selection resolution as the mount effect, for the
  // failure-state Retry action (and the reconnect re-arm): a retry that
  // succeeds must also migrate a stale stored selection, exactly like boot.
  function retryLoadProjects() {
    return loadProjects().then((list) => {
      if (list) resolveInitialProject(list, selectedProject, selectedSource, handleProjectChange, onNoProjects, storage);
      return list;
    });
  }

  // The failure screen owns its own recovery: while it shows, retry quietly
  // in the background — see hooks/useProjectAutoRetry.js.
  useProjectAutoRetry({
    projectsLoadFailed, projectsLoaded, loadInFlightRef, listProjects,
    setWarmup, setProjects, setProjectsLoaded, setProjectsLoadFailed,
    selectedProject, selectedSource, handleProjectChange, onNoProjects, storage, autoRetryMs,
  });

  // Warm-up poll — see hooks/useProjectWarmupPoll.js.
  useProjectWarmupPoll({ projects, projectsLoaded, projectsLoadFailed, loadProjects, summaryPollMs });

  useEffect(() => {
    loadProjects().then((list) => {
      // Array (possibly empty -> onboarding) on success; null when the load
      // failed after retries -> do NOT force onboarding on a transient error.
      if (list) resolveInitialProject(list, selectedProject, selectedSource, handleProjectChange, onNoProjects, storage);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleProjectChange(name, source = DEFAULT_SOURCE) {
    persistProject(setSelectedProject, name, storage);
    persistSource(setSelectedSource, source, storage);
    setSelectedRun(DEFAULT_RUN);
  }

  function handleRunChange(runId) { setSelectedRun(runId); }

  function selectProjectAndRun(project, runId) {
    persistProject(setSelectedProject, project, storage);
    persistSource(setSelectedSource, DEFAULT_SOURCE, storage);
    setSelectedRun(runId || DEFAULT_RUN);
  }

  return {
    projects,
    warmup,
    projectsLoaded,
    projectsLoadFailed,
    retryLoadProjects,
    setProjects,
    selectedProject,
    selectedSource,
    selectedRun,
    setSelectedRun,
    loadProjects,
    handleProjectChange,
    handleRunChange,
    selectProjectAndRun,
  };
}
