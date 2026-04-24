/**
 * VirtualList — simple windowing virtualizer that reads per-row heights from
 * pretext measurements. Keeps only visible rows (plus overscan) in the DOM.
 *
 * Design notes:
 *   - The caller supplies `getEstimatedHeight(item)` which must be cheap and
 *     stable for a given item. Use pretext's `measureText` upstream to compute
 *     a realistic row height before the row is in the DOM.
 *   - Measured (rendered) heights override estimates once a row has mounted,
 *     so layout stays accurate even if the estimate is a few pixels off. A
 *     `ResizeObserver` catches post-mount reflows (expand/collapse, window
 *     resize) and updates the running offsets.
 *   - The component uses the window as its scroll container by default. Pass
 *     an explicit `scrollParent` (an element or its ref) if the list lives in
 *     a custom scroll region.
 *   - `overscan` rows are rendered above and below the visible window so
 *     scrolls stay smooth.
 *
 * This is not a full-featured virtualizer (no sticky rows, no horizontal
 * virtualization, no reverse scroll). It's a purpose-built tool for quodeq's
 * single-column findings list where rows are tall and text-dense.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

const DEFAULT_OVERSCAN = 4;

function normaliseScrollParent(parent) {
  if (!parent) return null;
  if (parent.current !== undefined) return parent.current;
  return parent;
}

function getScrollTop(scrollEl) {
  if (!scrollEl || scrollEl === window) {
    return window.scrollY || document.documentElement.scrollTop || 0;
  }
  return scrollEl.scrollTop || 0;
}

function getViewportHeight(scrollEl) {
  if (!scrollEl || scrollEl === window) return window.innerHeight;
  return scrollEl.clientHeight;
}

export default function VirtualList({
  items,
  getEstimatedHeight,
  renderItem,
  getItemKey,
  overscan = DEFAULT_OVERSCAN,
  scrollParent,
  className,
  style,
}) {
  const containerRef = useRef(null);
  const rowRefs = useRef(new Map());
  const [measured, setMeasured] = useState(() => new Map());
  const [scrollTop, setScrollTop] = useState(0);
  const [containerTop, setContainerTop] = useState(0);
  const [viewport, setViewport] = useState(() => (typeof window === 'undefined' ? 0 : window.innerHeight));

  const scrollEl = useMemo(() => normaliseScrollParent(scrollParent) || (typeof window !== 'undefined' ? window : null), [scrollParent]);

  // ── offsets & total height, derived from measured-or-estimated per row ──
  const { offsets, totalHeight } = useMemo(() => {
    const arr = new Array(items.length + 1);
    arr[0] = 0;
    for (let i = 0; i < items.length; i++) {
      const key = getItemKey ? getItemKey(items[i], i) : i;
      const m = measured.get(key);
      const h = typeof m === 'number' && m > 0 ? m : Math.max(1, getEstimatedHeight(items[i], i) || 0);
      arr[i + 1] = arr[i] + h;
    }
    return { offsets: arr, totalHeight: arr[arr.length - 1] };
  }, [items, measured, getEstimatedHeight, getItemKey]);

  // ── scroll + viewport tracking ──
  const syncGeometry = useCallback(() => {
    setScrollTop(getScrollTop(scrollEl));
    setViewport(getViewportHeight(scrollEl));
    const el = containerRef.current;
    if (el) {
      if (scrollEl === window || !scrollEl) {
        setContainerTop(el.getBoundingClientRect().top + (window.scrollY || 0));
      } else {
        setContainerTop(el.offsetTop);
      }
    }
  }, [scrollEl]);

  useLayoutEffect(() => { syncGeometry(); }, [syncGeometry, items.length]);

  useEffect(() => {
    if (!scrollEl) return undefined;
    const onScroll = () => setScrollTop(getScrollTop(scrollEl));
    const onResize = () => { setViewport(getViewportHeight(scrollEl)); syncGeometry(); };
    scrollEl.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onResize);
    return () => {
      scrollEl.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onResize);
    };
  }, [scrollEl, syncGeometry]);

  // ── compute visible window ──
  const { startIndex, endIndex } = useMemo(() => {
    if (items.length === 0) return { startIndex: 0, endIndex: -1 };
    const topInList = Math.max(0, scrollTop - containerTop);
    const bottomInList = topInList + viewport;
    // offsets is strictly increasing; binary search the start.
    let lo = 0;
    let hi = items.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (offsets[mid + 1] <= topInList) lo = mid + 1;
      else if (offsets[mid] > topInList) hi = mid - 1;
      else { lo = mid; break; }
    }
    const first = Math.max(0, lo - overscan);
    let last = first;
    while (last < items.length - 1 && offsets[last + 1] < bottomInList) last += 1;
    last = Math.min(items.length - 1, last + overscan);
    return { startIndex: first, endIndex: last };
  }, [items.length, scrollTop, containerTop, viewport, offsets, overscan]);

  // ── post-mount measurement via ResizeObserver ──
  const observerRef = useRef(null);
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver((entries) => {
      let changed = false;
      const next = new Map(measured);
      for (const entry of entries) {
        const keyAttr = entry.target.dataset?.virtualKey;
        if (keyAttr == null) continue;
        const key = entry.target.__virtualKeyRef?.current ?? keyAttr;
        const h = entry.contentRect.height;
        if (h > 0 && next.get(key) !== h) {
          next.set(key, h);
          changed = true;
        }
      }
      if (changed) setMeasured(next);
    });
    observerRef.current = ro;
    return () => { ro.disconnect(); observerRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const registerRow = useCallback((key, el) => {
    const prev = rowRefs.current.get(key);
    if (prev === el) return;
    if (prev && observerRef.current) observerRef.current.unobserve(prev);
    if (el) {
      rowRefs.current.set(key, el);
      if (observerRef.current) observerRef.current.observe(el);
    } else {
      rowRefs.current.delete(key);
    }
  }, []);

  // ── render ──
  const visible = [];
  for (let i = startIndex; i <= endIndex; i++) {
    if (i < 0 || i >= items.length) continue;
    const item = items[i];
    const key = getItemKey ? getItemKey(item, i) : i;
    const top = offsets[i];
    visible.push(
      <div
        key={key}
        data-virtual-key={key}
        data-virtual-index={i}
        ref={(el) => registerRow(key, el)}
        style={{ position: 'absolute', left: 0, right: 0, top }}
      >
        {renderItem(item, i)}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ ...style, position: 'relative', height: totalHeight }}
    >
      {visible}
    </div>
  );
}
