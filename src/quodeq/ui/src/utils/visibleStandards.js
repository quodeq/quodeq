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

/** Write the selection to the local cache. The server is the source of truth. */
export function writeVisibleStandardIds(ids, storage = localStorage) {
  storage.setItem(VISIBLE_STANDARDS_STORAGE_KEY, JSON.stringify(ids));
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
 * `isStale` guards against a race: if the caller fires this for project A
 * and the user switches to project B before the request resolves, A's
 * response must not land in the (per-browser, not per-project) cache over
 * B's. Pass a function that returns true once the selection this call was
 * for is no longer the current one; it's checked right before every write,
 * including the migration PUT, so a stale call is a no-op past that point.
 */
export async function hydrateVisibleStandardIds(projectId, { storage = localStorage, isStale } = {}) {
  if (!projectId) return readVisibleStandardIds(storage);
  try {
    const { visibleStandardIds, isDefault } = await getStandardsVisibility(projectId);
    if (isStale?.()) return readVisibleStandardIds(storage);
    const cachedRaw = storage.getItem(VISIBLE_STANDARDS_STORAGE_KEY);
    if (isDefault && cachedRaw) {
      const cached = JSON.parse(cachedRaw);
      if (Array.isArray(cached)) {
        const saved = await putStandardsVisibility(projectId, cached);
        if (isStale?.()) return readVisibleStandardIds(storage);
        const ids = saved?.visibleStandardIds ?? cached;
        writeVisibleStandardIds(ids, storage);
        return ids;
      }
    }
    writeVisibleStandardIds(visibleStandardIds, storage);
    return visibleStandardIds;
  } catch {
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
