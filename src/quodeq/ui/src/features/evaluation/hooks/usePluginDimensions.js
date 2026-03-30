import { useState, useEffect } from 'react';
import { listPlugins, listStandards } from '../../../api/index.js';

export function usePluginDimensions() {
  const [allDimensions, setAllDimensions] = useState([]);
  const [dimLoadError, setDimLoadError] = useState(null);

  useEffect(() => {
    Promise.all([
      listPlugins().catch(() => []),
      listStandards().catch(() => []),
    ]).then(([plugins, standards]) => {
      const seen = new Map();

      // Add plugin dimensions first
      for (const p of plugins) {
        for (const d of p.dimensions) {
          if (!seen.has(d.id)) seen.set(d.id, d);
        }
      }

      // Merge custom and community standards as selectable dimensions
      for (const s of standards) {
        if (s.type === 'custom' || s.type === 'community') {
          if (!seen.has(s.id)) {
            seen.set(s.id, {
              id: s.id,
              label: s.name,
              iso_25010: null,
              standardType: s.type,
            });
          }
        }
      }

      setAllDimensions([...seen.values()]);
      setDimLoadError(null);
    }).catch((err) => {
      console.warn('Failed to load dimensions:', err);
      setAllDimensions([]);
      setDimLoadError('Failed to load dimensions. Using defaults.');
    });
  }, []);

  return { allDimensions, dimLoadError };
}
