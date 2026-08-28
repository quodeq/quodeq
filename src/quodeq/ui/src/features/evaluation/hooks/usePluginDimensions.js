import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { STANDARD_TYPES } from '../../standards/hooks/useStandards.js';
import { t } from '../../../strings/index.js';

function mergeStandardsDimensions(standards, seen) {
  for (const s of standards) {
    if (seen.has(s.id)) {
      const existing = seen.get(s.id);
      if (!existing.standardType) {
        existing.standardType = s.type === STANDARD_TYPES.BUILTIN ? null : s.type;
        if (s.name && !existing.label) existing.label = s.name;
      }
    } else if (s.type === STANDARD_TYPES.CUSTOM || s.type === STANDARD_TYPES.COMMUNITY || s.type === STANDARD_TYPES.QUODEQ) {
      seen.set(s.id, { id: s.id, label: s.name, iso_25010: null, standardType: s.type });
    }
  }
}

function deduplicateDimensions(plugins, standards) {
  const seen = new Map();
  for (const p of plugins) {
    for (const d of p.dimensions) {
      if (!seen.has(d.id)) seen.set(d.id, d);
    }
  }
  mergeStandardsDimensions(standards, seen);
  return seen;
}

/**
 * Load-once cache for the merged plugin+standards dimension list.
 *
 * Instance-scoped state (was two module-level variables) so tests can build
 * an isolated cache instead of inheriting whichever load happened first in
 * the process. `load` single-flights: concurrent callers share one in-flight
 * promise, and a failed load clears it so the next mount can retry.
 */
export function createDimensionCache() {
  let cachedDimensions = null;
  let cachePromise = null;
  return {
    /** Synchronously return the loaded list, or null before first load. */
    get() {
      return cachedDimensions;
    },
    load(listPlugins, listStandards) {
      if (cachePromise) return cachePromise;
      cachePromise = Promise.all([
        listPlugins().catch(() => []),
        listStandards().catch(() => []),
      ]).then(([plugins, standards]) => {
        const seen = deduplicateDimensions(plugins, standards);
        cachedDimensions = [...seen.values()];
        return cachedDimensions;
      }).catch((err) => {
        console.warn('Failed to load dimensions:', err);
        cachePromise = null; // allow retry on next mount
        return [];
      });
      return cachePromise;
    },
    invalidate() {
      cachedDimensions = null;
      cachePromise = null;
    },
  };
}

// Default instance: loaded once, reused across mounts — the pre-factory
// module-level behavior every production consumer relies on.
const defaultDimensionCache = createDimensionCache();

export function invalidateDimensionCache() {
  defaultDimensionCache.invalidate();
}

function _filterVisible(dims) {
  // Lowercase both sides: the server normalizes stored ids to lowercase,
  // but custom/imported standard ids aren't charset-constrained (e.g.
  // "OWASP-Top10"), so a raw comparison would drop a visible standard from
  // the scan dimension picker while the assistant and dashboard correctly
  // keep it.
  const visibleSet = new Set(readVisibleStandardIds().map((id) => id.toLowerCase()));
  return dims.filter((d) => visibleSet.has((d.id || '').toLowerCase()));
}

/**
 * Loads and caches all plugin dimensions, filtering by visible standard IDs.
 * @param {ReturnType<typeof createDimensionCache>} [cache] test seam;
 *   defaults to the shared module singleton.
 * @returns {{ allDimensions: Array, dimLoadError: string|null }}
 */
export function usePluginDimensions(cache = defaultDimensionCache) {
  const { listPlugins, listStandards } = useApi();
  const [allDimensions, setAllDimensions] = useState(() => {
    const cached = cache.get();
    return cached ? _filterVisible(cached) : [];
  });
  const [dimLoadError, setDimLoadError] = useState(null);

  useEffect(() => {
    const cached = cache.get();
    if (cached) {
      setAllDimensions(_filterVisible(cached));
      return;
    }
    cache.load(listPlugins, listStandards).then((dims) => {
      setAllDimensions(_filterVisible(dims));
      setDimLoadError(null);
    }).catch(() => {
      setDimLoadError(t('evaluate.dimensionsLoadFailed'));
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- mount-only, matching the pre-factory behavior

  return { allDimensions, dimLoadError };
}
