import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { STANDARD_TYPES } from '../../standards/hooks/useStandards.js';

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

// Module-level cache: loaded once, reused across mounts
let _cachedDimensions = null;
let _cachePromise = null;

function _loadDimensions(listPlugins, listStandards) {
  if (_cachePromise) return _cachePromise;
  _cachePromise = Promise.all([
    listPlugins().catch(() => []),
    listStandards().catch(() => []),
  ]).then(([plugins, standards]) => {
    const seen = deduplicateDimensions(plugins, standards);
    _cachedDimensions = [...seen.values()];
    return _cachedDimensions;
  }).catch((err) => {
    console.warn('Failed to load dimensions:', err);
    _cachePromise = null; // allow retry on next mount
    return [];
  });
  return _cachePromise;
}

export function invalidateDimensionCache() {
  _cachedDimensions = null;
  _cachePromise = null;
}

function _filterVisible(dims) {
  const visibleSet = new Set(readVisibleStandardIds());
  return dims.filter((d) => visibleSet.has(d.id));
}

/**
 * Loads and caches all plugin dimensions, filtering by visible standard IDs.
 * @returns {{ allDimensions: Array, dimLoadError: string|null }}
 */
export function usePluginDimensions() {
  const { listPlugins, listStandards } = useApi();
  const [allDimensions, setAllDimensions] = useState(() => _cachedDimensions ? _filterVisible(_cachedDimensions) : []);
  const [dimLoadError, setDimLoadError] = useState(null);

  useEffect(() => {
    if (_cachedDimensions) {
      setAllDimensions(_filterVisible(_cachedDimensions));
      return;
    }
    _loadDimensions(listPlugins, listStandards).then((dims) => {
      setAllDimensions(_filterVisible(dims));
      setDimLoadError(null);
    }).catch(() => {
      setDimLoadError('Failed to load dimensions. Try refreshing the page or check that the server is running.');
    });
  }, []);

  return { allDimensions, dimLoadError };
}
