import { useState, useEffect } from 'react';
import { listPlugins } from '../../../api/index.js';

export function usePluginDimensions() {
  const [allDimensions, setAllDimensions] = useState([]);
  const [dimLoadError, setDimLoadError] = useState(null);

  useEffect(() => {
    listPlugins()
      .then((plugins) => {
        const seen = new Map();
        for (const p of plugins) {
          for (const d of p.dimensions) {
            if (!seen.has(d.id)) seen.set(d.id, d);
          }
        }
        setAllDimensions([...seen.values()]);
        setDimLoadError(null);
      })
      .catch((err) => {
        console.warn('Failed to load dimensions:', err);
        setAllDimensions([]);
        setDimLoadError('Failed to load dimensions. Using defaults.');
      });
  }, []);

  return { allDimensions, dimLoadError };
}
