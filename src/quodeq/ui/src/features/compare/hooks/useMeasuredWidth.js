import { useLayoutEffect, useRef, useState } from 'react';

/**
 * The rendered pixel width of an element, kept current with ResizeObserver,
 * so SVG charts draw at their real size (the plot fills its panel and text
 * never scales). Returns [ref, width]; `width` starts at `fallback` (also
 * what test environments without ResizeObserver keep). Pass `ready` when
 * the element only mounts once data arrives, so the observer attaches then.
 */
export function useMeasuredWidth(fallback, ready = true) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.floor(entry.contentRect.width));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ready]);
  return [ref, width];
}
