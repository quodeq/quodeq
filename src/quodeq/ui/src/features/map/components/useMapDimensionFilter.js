import { useState, useMemo } from 'react';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { writeCachedState } from '../../../utils/pageStateCache.js';

/**
 * Dimension visibility + the map's own selection filter on top of it.
 * Selection defaults to all visible; an empty set means "no filter applied"
 * (show all), and the selection persists across unmount as an array.
 */
export function useMapDimensionFilter({ allDimensions, selectedProject, cachedSelectedArr }) {
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

  const [selectedDimensions, _setSelectedDimensions] = useState(() => new Set(cachedSelectedArr));
  const setSelectedDimensions = (updater) => {
    _setSelectedDimensions((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      writeCachedState('map', selectedProject, { selectedDimensionsArr: Array.from(next) });
      return next;
    });
  };
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
