import { useLayoutEffect, useRef, useState } from 'react';

/**
 * A value read from an element's rendered box, kept current with
 * ResizeObserver. `read(contentRect, prev)` returns the next value, or prev
 * to skip an update (zero sizes while hidden, say). Starts at `fallback`,
 * which test environments without ResizeObserver keep. Pass `ready` when the
 * element only mounts once data arrives, so the observer attaches then.
 */
function useMeasured(read, fallback, ready) {
  const ref = useRef(null);
  const [value, setValue] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(([entry]) => setValue((prev) => read(entry.contentRect, prev)));
    ro.observe(el);
    return () => ro.disconnect();
    // `read` is a module-level function; only `ready` re-attaches the observer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);
  return [ref, value];
}

const readWidth = (rect, prev) => (rect.width > 0 ? Math.floor(rect.width) : prev);

function readSize(rect, prev) {
  const width = Math.floor(rect.width);
  const height = Math.floor(rect.height);
  if (width <= 0 || height <= 0) return prev;
  return prev.width === width && prev.height === height ? prev : { width, height };
}

/**
 * The rendered pixel width of an element, so SVG charts draw at their real
 * size (the plot fills its panel and text never scales). Returns [ref, width].
 */
export function useMeasuredWidth(fallback, ready = true) {
  return useMeasured(readWidth, fallback, ready);
}

/**
 * The rendered width and height, for a chart that fills a box its layout
 * sizes (the direction map takes the height its row gives it).
 * Returns [ref, {width, height}].
 */
export function useMeasuredSize(fallback) {
  return useMeasured(readSize, fallback, true);
}
