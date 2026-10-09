import { useEffect, useRef, useState } from 'react';

/**
 * Columns that spread `count` cards evenly over the rows they need: 9 cards
 * that fit 8 across become 5 + 4, never 8 + 1. Pure, for the hook below.
 */
export function balancedColumns(count, width, minCard, gap) {
  if (count <= 0 || width <= 0) return null;
  const fit = Math.max(1, Math.floor((width + gap) / (minCard + gap)));
  const rows = Math.ceil(count / fit);
  return Math.ceil(count / rows);
}

/**
 * A ref for the grid and the inline style that sets its balanced column
 * count, kept current as the grid resizes. No style until measured, so the
 * stylesheet's auto-fit layout shows meanwhile.
 */
export function useBalancedColumns(count, minCard, gap) {
  const ref = useRef(null);
  const [cols, setCols] = useState(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const measure = () => setCols(balancedColumns(count, el.clientWidth, minCard, gap));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [count, minCard, gap]);
  return [ref, cols ? { gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` } : undefined];
}
