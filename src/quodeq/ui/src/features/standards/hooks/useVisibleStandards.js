import { useState, useCallback, useMemo } from 'react';
import { VISIBLE_STANDARDS_STORAGE_KEY } from '../../../constants.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';

function writeToStorage(ids, storage = localStorage) {
  storage.setItem(VISIBLE_STANDARDS_STORAGE_KEY, JSON.stringify(ids));
}

export function useVisibleStandards({ storage = localStorage } = {}) {
  const [visibleIds, setVisibleIds] = useState(readVisibleStandardIds);

  const toggle = useCallback((id) => {
    setVisibleIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      writeToStorage(next, storage);
      return next;
    });
  }, [storage]);

  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  const isVisible = useCallback((id) => visibleSet.has(id), [visibleSet]);

  const add = useCallback((id) => {
    setVisibleIds((prev) => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      writeToStorage(next, storage);
      return next;
    });
  }, [storage]);

  const remove = useCallback((id) => {
    setVisibleIds((prev) => {
      if (!prev.includes(id)) return prev;
      const next = prev.filter((x) => x !== id);
      writeToStorage(next, storage);
      return next;
    });
  }, [storage]);

  return { visibleIds, toggle, isVisible, add, remove };
}
