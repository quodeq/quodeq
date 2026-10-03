/**
 * Coalesces per-project compare-summary lookups into fleet requests.
 *
 * The Compare tab keeps one react-query entry per project (so every
 * project-scoped invalidation still reaches its row), but the server answers
 * the whole fleet in one request. The loader bridges the two: every lookup
 * started in the same tick joins one `fetchFleet(ids)` call, and each
 * caller's promise settles from that response, with the summary when the
 * server returned one, with an error when the project is in `errors` (or,
 * should the server name it nowhere, the Compare row's generic failure).
 *
 * A single invalidated row therefore costs one fleet request of one project,
 * and the first visit costs one request for the whole fleet.
 */
import { t } from '../strings/index.js';

const LOAD_FAILED_KEY = 'compare.loadFailed';

/**
 * @param {(ids: string[]) => Promise<{summaries: Array<{project: string}>, errors: Object<string, string>}>} fetchFleet
 * @returns {(projectId: string) => Promise<Object>}
 */
export function makeFleetCompareLoader(fetchFleet) {
  let pending = null;

  function settle(waiters, response) {
    const byProject = new Map((response?.summaries || []).map((s) => [s.project, s]));
    const errors = response?.errors || {};
    waiters.forEach((list, id) => {
      const summary = byProject.get(id);
      list.forEach(({ resolve, reject }) => {
        if (summary !== undefined) resolve(summary);
        else reject(new Error(errors[id] || t(LOAD_FAILED_KEY)));
      });
    });
  }

  function flush() {
    const waiters = pending;
    pending = null;
    const rejectAll = (err) => waiters.forEach((list) => list.forEach(({ reject }) => reject(err)));
    // Both outcomes settle the waiters; nothing is left for a caller to await.
    void fetchFleet([...waiters.keys()]).then((response) => settle(waiters, response), rejectAll);
  }

  return (projectId) =>
    new Promise((resolve, reject) => {
      if (!pending) {
        pending = new Map();
        setTimeout(flush, 0);
      }
      const list = pending.get(projectId) || [];
      list.push({ resolve, reject });
      pending.set(projectId, list);
    });
}
