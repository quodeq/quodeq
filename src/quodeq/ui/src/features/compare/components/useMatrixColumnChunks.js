import { useEffect, useRef, useState } from 'react';

// Rough per-column geometry for the wrap computation: the lead column
// (stripe + rank + name) and one score column, in px. Estimates, not
// measurements — the wrap point only needs to be approximately right.
const LEAD_W = 250;
const COL_W = 62;
const MIN_CHUNK = 2;

/**
 * Distributes columns that don't fit the panel into stacked groups instead
 * of scrolling: the first group also carries the overall column (one
 * slot), later groups repeat only the lead. Group size comes from a
 * ResizeObserver on the scroll container returned as `wrapRef`.
 */
export function useMatrixColumnChunks(columns, hasData) {
  const wrapRef = useRef(null);
  // Columns per group. Infinity until the container reports a width (and
  // forever in environments without layout), i.e. no wrapping.
  const [chunkCap, setChunkCap] = useState(Infinity);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const compute = () => {
      const w = el.clientWidth;
      if (!w) return;
      setChunkCap(Math.max(MIN_CHUNK, Math.floor((w - LEAD_W) / COL_W)));
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    return () => ro.disconnect();
    // Re-arm when the grid appears: on first mount the data guard the
    // caller applies before rendering returns null, the ref is unattached,
    // and a mount-only effect would observe nothing forever.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasData]);

  const chunks = [];
  let i = 0;
  let first = true;
  while (i < columns.length) {
    const cap = Math.max(1, first ? chunkCap - 1 : chunkCap);
    chunks.push(columns.slice(i, i + cap));
    i += cap;
    first = false;
  }

  return { wrapRef, chunks };
}
