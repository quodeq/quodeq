import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { STANDARD_TYPES } from '../../standards/hooks/useStandards.js';
import { t } from '../../../strings/index.js';
import { STANDARDS_CHANGED_EVENT, STANDARDS_CHANGED_REASON } from '../../../constants.js';

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
  let refreshPromise = null;
  function load(listPlugins, listStandards) {
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
        // Surface the failure instead of swallowing it to `[]` -- the only
        // production caller (usePluginDimensions below) has its own
        // .catch() that sets dimLoadError, which never fired while this
        // resolved unconditionally. listPlugins/listStandards already
        // degrade individually (see the per-call .catch above), so this
        // only rejects on a genuinely unexpected failure (e.g. malformed
        // plugin/standard data breaking dedup) -- worth surfacing rather
        // than silently showing an empty dimension list.
        throw err;
      });
      return cachePromise;
  }
  function invalidate() {
    cachedDimensions = null;
    cachePromise = null;
  }
  return {
    /** Synchronously return the loaded list, or null before first load. */
    get() {
      return cachedDimensions;
    },
    load,
    invalidate,
    /**
     * Drop the cached list and reload. Single-flighted separately from
     * `load`: every mounted picker reacts to the same change event, and
     * without this each one would invalidate the other's in-flight load.
     */
    refresh(listPlugins, listStandards) {
      if (refreshPromise) return refreshPromise;
      invalidate();
      refreshPromise = load(listPlugins, listStandards).finally(() => { refreshPromise = null; });
      return refreshPromise;
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
  const visibleSet = _visibleSet();
  return dims.filter((d) => visibleSet.has((d.id || '').toLowerCase()));
}

function _visibleSet() {
  return new Set(readVisibleStandardIds().map((id) => id.toLowerCase()));
}

/**
 * True when the visible set names a standard the cached list has never
 * seen: a file dropped into the evaluators dir after the picker loaded and
 * then starred on the Standards page. Refiltering the cache cannot surface
 * it; only a refetch can.
 */
function _cacheMissesVisible(dims) {
  const known = new Set(dims.map((d) => (d.id || '').toLowerCase()));
  for (const id of _visibleSet()) {
    if (!known.has(id)) return true;
  }
  return false;
}

/**
 * Loads and caches all plugin dimensions, filtering by visible standard IDs.
 * @param {ReturnType<typeof createDimensionCache>} [cache] test seam;
 *   defaults to the shared module singleton.
 * @returns {{ allDimensions: Array, dimLoadError: string|null }}
 */
function _applyLoad(promise, setAllDimensions, setDimLoadError) {
  return promise.then((dims) => {
    setAllDimensions(_filterVisible(dims));
    setDimLoadError(null);
  }).catch(() => {
    setDimLoadError(t('evaluate.dimensionsLoadFailed'));
  });
}

export function usePluginDimensions(cache = defaultDimensionCache) {
  const { listPlugins, listStandards } = useApi();
  const [allDimensions, setAllDimensions] = useState(() => {
    const cached = cache.get();
    return cached ? _filterVisible(cached) : [];
  });
  const [dimLoadError, setDimLoadError] = useState(null);

  useEffect(() => {
    const cached = cache.get();
    if (cached && !_cacheMissesVisible(cached)) {
      setAllDimensions(_filterVisible(cached));
      return;
    }
    const load = cached ? cache.refresh(listPlugins, listStandards) : cache.load(listPlugins, listStandards);
    _applyLoad(load, setAllDimensions, setDimLoadError);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- mount-only, matching the pre-factory behavior

  // The list above is filtered once per mount. A star toggle, a project
  // switch (visibility re-hydrates) or a created / imported / duplicated /
  // deleted standard has to reach a picker that is already on screen.
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onChanged = (evt) => {
      const cached = cache.get();
      if (evt?.detail?.reason === STANDARDS_CHANGED_REASON.VISIBILITY && cached && !_cacheMissesVisible(cached)) {
        setAllDimensions(_filterVisible(cached));
        return;
      }
      _applyLoad(cache.refresh(listPlugins, listStandards), setAllDimensions, setDimLoadError);
    };
    window.addEventListener(STANDARDS_CHANGED_EVENT, onChanged);
    return () => window.removeEventListener(STANDARDS_CHANGED_EVENT, onChanged);
  }, [cache, listPlugins, listStandards]);

  return { allDimensions, dimLoadError };
}
