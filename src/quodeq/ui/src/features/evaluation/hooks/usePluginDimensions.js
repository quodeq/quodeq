import { useState, useEffect } from 'react';
import { listPlugins, listStandards } from '../../../api/index.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';

function mergeStandardsDimensions(standards, seen) {
  for (const s of standards) {
    if (seen.has(s.id)) {
      const existing = seen.get(s.id);
      if (!existing.standardType) {
        existing.standardType = s.type === 'builtin' ? null : s.type;
        if (s.name && !existing.label) existing.label = s.name;
      }
    } else if (s.type === 'custom' || s.type === 'community' || s.type === 'quodeq') {
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

export function usePluginDimensions() {
  const [allDimensions, setAllDimensions] = useState([]);
  const [dimLoadError, setDimLoadError] = useState(null);

  useEffect(() => {
    Promise.all([
      listPlugins().catch(() => []),
      listStandards().catch(() => []),
    ]).then(([plugins, standards]) => {
      const seen = deduplicateDimensions(plugins, standards);
      const visibleSet = new Set(readVisibleStandardIds());
      setAllDimensions([...seen.values()].filter((d) => visibleSet.has(d.id)));
      setDimLoadError(null);
    }).catch((err) => {
      console.warn('Failed to load dimensions:', err);
      setAllDimensions([]);
      setDimLoadError('Failed to load dimensions. Using defaults.');
    });
  }, []);

  return { allDimensions, dimLoadError };
}
