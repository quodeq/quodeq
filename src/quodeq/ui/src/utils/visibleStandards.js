import { VISIBLE_STANDARDS_STORAGE_KEY, DEFAULT_VISIBLE_STANDARDS } from '../constants.js';
import { getStandardsVisibility, putStandardsVisibility } from '../api/standards.js';

/**
 * Read the visible standard IDs from localStorage.
 * Returns the default ISO dimensions if nothing is stored.
 */
export function readVisibleStandardIds(storage = localStorage) {
  try {
    const raw = storage.getItem(VISIBLE_STANDARDS_STORAGE_KEY);
    if (!raw) return DEFAULT_VISIBLE_STANDARDS;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : DEFAULT_VISIBLE_STANDARDS;
  } catch {
    return DEFAULT_VISIBLE_STANDARDS;
  }
}

// Monotonic counter bumped by every cache write (this module's own write and
// hydrate's two write sites). hydrateVisibleStandardIds samples it right
// before issuing its GET; if the counter has moved by the time a write would
// happen, some other write (a toggle's persist(), or another hydrate call)
// already landed a newer value, and this response is discarded instead of
// clobbering it.
//
// The counter is module state, so it is only safe across tests because each
// call compares against its own sample rather than an absolute value, AND
// every caller awaits its in-flight hydrate before the next one starts. A
// promise left dangling across a test boundary WOULD trip a later call's
// check. That invariant is not enforced structurally; if a second caller of
// hydrateVisibleStandardIds ever appears, or a test stops awaiting, export a
// test-only reset rather than relying on it.
let writeGeneration = 0;

/** Write the selection to the local cache. The server is the source of truth. */
export function writeVisibleStandardIds(ids, storage = localStorage) {
  storage.setItem(VISIBLE_STANDARDS_STORAGE_KEY, JSON.stringify(ids));
  writeGeneration += 1;
}

/**
 * Sync the local cache with the server for a project.
 *
 * localStorage is a cache so the 8 synchronous read sites keep working; the
 * file in the repo is authoritative. On the first run after upgrading, the
 * server has no file yet (isDefault) while the browser may hold a real
 * selection — that one gets pushed up rather than silently lost.
 *
 * Never throws: an offline/failed fetch leaves the cached value in place.
 *
 * Two independent guards run right before every write this function makes
 * (both the normal path and the migration path's post-PUT write):
 *
 * - `isStale` guards against the PROJECT changing: if the caller fires this
 *   for project A and the user switches to project B before the request
 *   resolves, A's response must not land in the (per-browser, not
 *   per-project) cache over B's. Pass a function that returns true once the
 *   selection this call was for is no longer the current one.
 * - The generation counter guards against a newer WRITE for the SAME
 *   project already having landed: e.g. this GET was in flight when the
 *   user toggled a standard, and persist() synchronously wrote and PUT the
 *   toggle before this GET resolved with pre-toggle server state. `isStale`
 *   alone can't catch this because the project never changed.
 */
export async function hydrateVisibleStandardIds(projectId, { storage = localStorage, isStale } = {}) {
  if (!projectId) return readVisibleStandardIds(storage);
  const generationAtStart = writeGeneration;
  const supersededByNewerWrite = () => isStale?.() || writeGeneration !== generationAtStart;
  try {
    const { visibleStandardIds, isDefault } = await getStandardsVisibility(projectId);
    if (supersededByNewerWrite()) return readVisibleStandardIds(storage);
    const cachedRaw = storage.getItem(VISIBLE_STANDARDS_STORAGE_KEY);
    if (isDefault && cachedRaw) {
      const cached = JSON.parse(cachedRaw);
      if (Array.isArray(cached)) {
        const saved = await putStandardsVisibility(projectId, cached);
        if (supersededByNewerWrite()) return readVisibleStandardIds(storage);
        const ids = saved?.visibleStandardIds ?? cached;
        writeVisibleStandardIds(ids, storage);
        return ids;
      }
    }
    writeVisibleStandardIds(visibleStandardIds, storage);
    return visibleStandardIds;
  } catch (err) {
    // Covers both an offline/failed fetch (expected, cache stays put) and a
    // genuine bug such as a response-shape change throwing a TypeError. The
    // two aren't cheaply distinguishable here (fetch failures and shape-change
    // errors can both surface as TypeError), so we warn for both rather than
    // let a real regression degrade invisibly to "serve stale cache forever".
    console.warn('hydrateVisibleStandardIds: falling back to cached value', err);
    return readVisibleStandardIds(storage);
  }
}

/**
 * Compute summary stats from a filtered dimensions array.
 */
export function computeSummaryFromDimensions(dimensions) {
  let totalViolations = 0;
  let totalCompliance = 0;
  const severity = { critical: 0, major: 0, minor: 0 };
  for (const d of dimensions) {
    const violations = d.violations || [];
    totalViolations += violations.length;
    totalCompliance += d.compliance?.length || 0;
    for (const v of violations) {
      const s = (v.severity || '').toLowerCase();
      if (s === 'critical') severity.critical++;
      else if (s === 'major') severity.major++;
      else if (s === 'minor') severity.minor++;
    }
  }
  return { totalViolations, totalCompliance, severity };
}
