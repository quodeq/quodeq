import { VISIBLE_STANDARDS_STORAGE_KEY, DEFAULT_VISIBLE_STANDARDS } from '../constants.js';
import { getStandardsVisibility, putStandardsVisibility } from '../api/standards.js';
import { countBySeverity } from './severity.js';
import { readJSON, writeString } from '../adapters/storage.js';
import { decideHydration } from './visibleStandardsModel.js';

// Marks that the (per-browser, not per-project) cache has been reconciled
// with SOME project's own real file -- either because that project already
// had one (isDefault: false) or because the one-time legacy migration below
// just created one. Once set, the migration below never fires again: a
// later project with no file of its own must read as "give me the ISO
// defaults", not "adopt whatever the previous project's cache happens to
// hold". Stored in `storage` (not module state) so it rides along with
// whichever cache it governs, including in tests that inject their own
// fake storage per test.
const VISIBLE_STANDARDS_MIGRATED_KEY = 'quodeq-visible-standards-migrated';

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
// The counter is module state: each call compares against its own sample
// rather than an absolute value, and every caller awaits its in-flight
// hydrate before the next one starts. A promise left dangling across a test
// boundary would otherwise trip a later call's check, so `resetWriteGeneration`
// below exists as the structural escape hatch that note used to only ask for.
let writeGeneration = 0;

/** Reset the write generation. Test-isolation hook; returns the new value. */
export function resetWriteGeneration() {
  writeGeneration = 0;
  return writeGeneration;
}

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
 * selection — that one gets pushed up rather than silently lost. This
 * migration is one-shot and per-BROWSER, not per-project: it only fires
 * while the cache (a) actually differs from the ISO defaults (nothing to
 * migrate otherwise) and (b) has never been reconciled with any project's
 * own real file yet (`VISIBLE_STANDARDS_MIGRATED_KEY`). Once either has
 * happened once, a later project with no file of its own gets the plain ISO
 * defaults, never another project's ids -- without guard (b), switching
 * from a project with a real selection to one with none would otherwise
 * "migrate" the first project's ids into the second project's brand-new
 * file every time.
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
    const { visibleStandardIds, isDefault, defaultStandardIds } = await getStandardsVisibility(projectId);
    if (supersededByNewerWrite()) return readVisibleStandardIds(storage);
    // Migration/adoption policy lives in decideHydration (visibleStandardsModel.js);
    // this orchestrator only fetches, guards the two races below, and executes
    // the storage writes the decision calls for.
    const decision = decideHydration({
      serverIds: visibleStandardIds,
      isDefault,
      serverDefaults: defaultStandardIds,
      cachedIds: readJSON(VISIBLE_STANDARDS_STORAGE_KEY, null, storage),
      alreadyMigrated: !!storage.getItem(VISIBLE_STANDARDS_MIGRATED_KEY),
      fallbackDefaults: DEFAULT_VISIBLE_STANDARDS,
    });
    if (decision.kind === 'migrate') {
      const saved = await putStandardsVisibility(projectId, decision.ids);
      if (supersededByNewerWrite()) return readVisibleStandardIds(storage);
      const ids = saved?.visibleStandardIds ?? decision.ids;
      writeString(VISIBLE_STANDARDS_MIGRATED_KEY, '1', storage);
      writeVisibleStandardIds(ids, storage);
      return ids;
    }
    if (decision.markMigrated) {
      // This project already has its own real file: the cache is now known
      // to belong to a specific project's synced selection, so it must
      // never again be read as an unclaimed legacy value up for grabs by
      // the next project that happens to have no file yet.
      writeString(VISIBLE_STANDARDS_MIGRATED_KEY, '1', storage);
    }
    writeVisibleStandardIds(decision.ids, storage);
    return decision.ids;
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
    const counts = countBySeverity(violations);
    severity.critical += counts.critical;
    severity.major += counts.major;
    severity.minor += counts.minor;
  }
  return { totalViolations, totalCompliance, severity };
}
