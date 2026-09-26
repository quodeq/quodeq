import { useState, useMemo, useEffect, useRef } from 'react';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { writeCachedState } from '../../../utils/pageStateCache.js';

/**
 * Mirrors the selection to the page-state cache so it survives unmount
 * (Map/Violations drop their subtree on drill-in). Runs as an effect, not
 * inside the state updater, so it stays a pure function of state and never
 * fires on the initial mount — only on a selection actually made this
 * session.
 *
 * `cache` is an optional injected page-state cache (see pageStateCache.js);
 * with none given this calls the module's own `writeCachedState`, so it
 * still goes through the shared default cache exactly as before.
 */
function useCacheSelectedDimensions(selectedProject, selectedDimensions, cache) {
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    const write = cache ? cache.writeCachedState : writeCachedState;
    write('map', selectedProject, { selectedDimensionsArr: Array.from(selectedDimensions) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDimensions]);
}

/**
 * Dimension visibility + the map's own selection filter on top of it.
 * Selection defaults to all visible; an empty set means "no filter applied"
 * (show all), and the selection persists across unmount as an array.
 * `cache` is an optional injected page-state cache; omit it to use the
 * shared default (see pageStateCache.js).
 */
export function useMapDimensionFilter({ allDimensions, selectedProject, cachedSelectedArr, cache }) {
  // Get visible standards and available dimension names. The ids are read on
  // every render and the Set is keyed on them, not on `allDimensions`: hiding
  // a standard elsewhere has to reach the map even when the same dimensions
  // come back in.
  const visibleIdList = readVisibleStandardIds();
  const visibleIdKey = visibleIdList.join(',');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const visibleIds = useMemo(() => new Set(visibleIdList), [visibleIdKey]);
  const visibleDimensions = useMemo(
    () => allDimensions.filter((d) => visibleIds.has((d.dimension || '').toLowerCase())),
    [allDimensions, visibleIds]
  );
  const dimensionNames = useMemo(
    () => visibleDimensions.map((d) => d.dimension).filter(Boolean).sort(),
    [visibleDimensions]
  );

  const [selectedDimensions, setSelectedDimensions] = useState(() => new Set(cachedSelectedArr));
  useCacheSelectedDimensions(selectedProject, selectedDimensions, cache);

  const effectiveSelected = useMemo(
    () => selectedDimensions.size === 0 ? new Set(dimensionNames) : selectedDimensions,
    [selectedDimensions, dimensionNames]
  );

  const handleToggleDimension = (dim) => {
    setSelectedDimensions((prev) => {
      const base = prev.size === 0 ? new Set(dimensionNames) : new Set(prev);
      if (base.has(dim)) {
        base.delete(dim);
        if (base.size === 0) return new Set();
      } else {
        base.add(dim);
      }
      if (base.size === dimensionNames.length) return new Set();
      return base;
    });
  };

  // Filter dimensions by selection
  const filteredDimensions = useMemo(
    () => visibleDimensions.filter((d) => effectiveSelected.has(d.dimension)),
    [visibleDimensions, effectiveSelected]
  );

  return { dimensionNames, effectiveSelected, handleToggleDimension, filteredDimensions };
}
