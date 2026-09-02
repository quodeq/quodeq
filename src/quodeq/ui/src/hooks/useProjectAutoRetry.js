import { useEffect } from 'react';
import { resolveInitialProject } from './projectStateStorage.js';

/**
 * useProjectState.js's background auto-retry effect: while the failure
 * screen shows, quietly retry in the background so a recovered backend
 * clears the failed state without the user clicking Retry. Extracted
 * verbatim.
 */
export function useProjectAutoRetry({
  projectsLoadFailed, projectsLoaded, loadInFlightRef, listProjects,
  setWarmup, setProjects, setProjectsLoaded, setProjectsLoadFailed,
  selectedProject, selectedSource, handleProjectChange, onNoProjects, storage, autoRetryMs,
}) {
  useEffect(() => {
    if (!projectsLoadFailed || projectsLoaded) return undefined;
    const id = setInterval(() => {
      if (loadInFlightRef.current) return;
      loadInFlightRef.current = true;
      listProjects()
        .then((data) => {
          const list = Array.isArray(data) ? data : (data?.projects || []);
          if (data && !Array.isArray(data)) setWarmup(data.warmup ?? null);
          setProjects(list);
          setProjectsLoaded(true);
          setProjectsLoadFailed(false);
          resolveInitialProject(list, selectedProject, selectedSource, handleProjectChange, onNoProjects, storage);
        })
        .catch(() => { /* still down: stay on the failed state, try again next tick */ })
        .finally(() => { loadInFlightRef.current = false; });
    }, autoRetryMs);
    return () => clearInterval(id);
  }, [projectsLoadFailed, projectsLoaded, autoRetryMs, listProjects]); // eslint-disable-line react-hooks/exhaustive-deps
}
