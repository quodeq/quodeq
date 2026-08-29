import { useState, useEffect } from 'react';
import { listStandards } from '../../../api/standards.js';

/**
 * The map page's one data fetch: standard id → type, used for galaxy
 * constellation grouping. Isolated from useMapPageState so the fetch can be
 * exercised (or mocked) independently of the DOM/storage/tree concerns.
 *
 * @returns {{ standardTypes: Object<string, string> }} lowercased id → type
 *   ('custom' when the standard carries none); empty until the fetch lands,
 *   and stays empty when it fails (grouping then falls back gracefully).
 */
export function useVisibleStandards() {
  const [standardTypes, setStandardTypes] = useState({});
  useEffect(() => {
    listStandards().then(stds => {
      const map = {};
      stds.forEach(s => { map[(s.id || '').toLowerCase()] = s.type || 'custom'; });
      setStandardTypes(map);
    }).catch(() => {});
  }, []);
  return { standardTypes };
}
