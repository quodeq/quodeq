import { useState, useCallback, useMemo } from 'react';
import { readVisibleStandardIds, writeVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { putStandardsVisibility } from '../../../api/standards.js';

export function useVisibleStandards({ storage = localStorage, projectId = null } = {}) {
  const [visibleIds, setVisibleIds] = useState(readVisibleStandardIds);

  const persist = useCallback((next) => {
    writeVisibleStandardIds(next, storage);
    // Fire-and-forget: the cache is already updated, so a failed write leaves
    // the UI correct for this session and re-syncs on the next hydrate.
    if (projectId) putStandardsVisibility(projectId, next).catch(() => {});
  }, [storage, projectId]);

  const toggle = useCallback((id) => {
    setVisibleIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      persist(next);
      return next;
    });
  }, [persist]);

  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);
  const isVisible = useCallback((id) => visibleSet.has(id), [visibleSet]);

  const add = useCallback((id) => {
    setVisibleIds((prev) => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      persist(next);
      return next;
    });
  }, [persist]);

  const remove = useCallback((id) => {
    setVisibleIds((prev) => {
      if (!prev.includes(id)) return prev;
      const next = prev.filter((x) => x !== id);
      persist(next);
      return next;
    });
  }, [persist]);

  return { visibleIds, toggle, isVisible, add, remove };
}
