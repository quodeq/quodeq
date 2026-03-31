import { useState, useCallback, useMemo } from 'react';
import { VISIBLE_STANDARDS_STORAGE_KEY } from '../../../constants.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';

function writeToStorage(ids) {
  localStorage.setItem(VISIBLE_STANDARDS_STORAGE_KEY, JSON.stringify(ids));
}

export function useVisibleStandards() {
  const [visibleIds, setVisibleIds] = useState(readVisibleStandardIds);

  const toggle = useCallback((id) => {
    setVisibleIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      writeToStorage(next);
      return next;
    });
  }, []);

  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  const isVisible = useCallback((id) => visibleSet.has(id), [visibleSet]);

  const add = useCallback((id) => {
    setVisibleIds((prev) => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      writeToStorage(next);
      return next;
    });
  }, []);

  const remove = useCallback((id) => {
    setVisibleIds((prev) => {
      if (!prev.includes(id)) return prev;
      const next = prev.filter((x) => x !== id);
      writeToStorage(next);
      return next;
    });
  }, []);

  return { visibleIds, toggle, isVisible, add, remove };
}
