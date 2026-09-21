import { useEffect, useRef } from 'react';
import { resolveInitialProject } from './projectStateStorage.js';

// One retry attempt. Everything it needs beyond listProjects is read from
// `latest` at call time, so a selection change between ticks is picked up
// without the interval being torn down and restarted (which would reset the
// retry clock and could starve the retry entirely on a busy page).
function runRetryTick(listProjects, latest) {
  const { loadInFlightRef } = latest.current;
  if (loadInFlightRef.current) return;
  loadInFlightRef.current = true;
  listProjects()
    .then((data) => {
      const cur = latest.current;
      const list = Array.isArray(data) ? data : (data?.projects || []);
      cur.setProjects(list);
      cur.setProjectsLoaded(true);
      cur.setProjectsLoadFailed(false);
      resolveInitialProject({
        list,
        currentProject: cur.selectedProject,
        currentSource: cur.selectedSource,
        onChangeProject: cur.handleProjectChange,
        onNoProjects: cur.onNoProjects,
        storage: cur.storage,
      });
    })
    .catch((err) => {
      // Still down: stay on the failed state and try again next tick.
      console.warn('[useProjectAutoRetry] background retry failed:', err);
    })
    .finally(() => { loadInFlightRef.current = false; });
}

/**
 * While the project-list failure screen shows, quietly retry in the
 * background so a recovered backend clears the failed state without the user
 * clicking Retry. The interval only exists while the load has failed and has
 * not since succeeded.
 */
export function useProjectAutoRetry({
  projectsLoadFailed, projectsLoaded, loadInFlightRef, listProjects,
  setProjects, setProjectsLoaded, setProjectsLoadFailed,
  selectedProject, selectedSource, handleProjectChange, onNoProjects, storage, autoRetryMs,
}) {
  const latest = useRef(null);
  latest.current = {
    loadInFlightRef, setProjects, setProjectsLoaded, setProjectsLoadFailed,
    selectedProject, selectedSource, handleProjectChange, onNoProjects, storage,
  };

  useEffect(() => {
    if (!projectsLoadFailed || projectsLoaded) return undefined;
    const id = setInterval(() => runRetryTick(listProjects, latest), autoRetryMs);
    return () => clearInterval(id);
  }, [projectsLoadFailed, projectsLoaded, autoRetryMs, listProjects]);
}
