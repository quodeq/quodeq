import { useLayoutEffect, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

/**
 * The dashboard's main column owns vertical scroll; tanstack-virtual needs a
 * ref to that ancestor to track scroll position. The scroller is rendered by
 * the app shell outside the tab-keyed subtree, so it exists before any detail
 * page mounts — resolving it synchronously in the state initializer means the
 * first render already virtualizes instead of committing an empty (or worse,
 * complete) list for one frame.
 */
export function useDashboardScrollElement() {
  const [scrollElement] = useState(() =>
    typeof document !== 'undefined'
      ? document.querySelector('.app-shell__main-column > .dashboard')
      : null,
  );
  return scrollElement;
}

/**
 * The offset of `ref`'s element from the top of `scrollElement`'s content,
 * for VirtualList's `scrollMargin`. Re-measured whenever anything in the
 * scroller resizes, since content above the list moves it.
 */
export function useScrollMargin(ref, scrollElement) {
  const [margin, setMargin] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !scrollElement) return undefined;
    const measure = () => {
      const offset = el.getBoundingClientRect().top - scrollElement.getBoundingClientRect().top + scrollElement.scrollTop;
      setMargin((cur) => (Math.abs(cur - offset) < 1 ? cur : offset));
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    for (const child of scrollElement.children) observer.observe(child);
    return () => observer.disconnect();
  }, [ref, scrollElement]);
  return margin;
}

/**
 * Absolutely-positioned virtual list over a flattened items array (headers
 * and rows mixed in one list, so one scroller virtualizes the whole page).
 *
 * Remount it (via `key`) when the items collection changes shape: a fresh
 * useVirtualizer call begins with no cached heights, so the row wrappers
 * re-measure from scratch — eliminating overlap caused by stale measurements
 * lingering from a previous filter or dismiss state.
 *
 * Without a scroll container (no `.dashboard` ancestor in the DOM — a moved
 * shell or a jsdom test) it degrades to a plain fully-rendered list rather
 * than rendering nothing.
 *
 * `scrollMargin` is the list's distance from the top of the scroller's
 * content. A list that starts below other content needs it (see
 * useScrollMargin), or the virtualizer picks the rows for the wrong slice.
 */
export default function VirtualList({ items, scrollElement, estimateSize, getItemKey, renderItem, overscan = 6, label, scrollMargin = 0 }) {
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollElement,
    estimateSize,
    overscan,
    getItemKey,
    scrollMargin,
  });

  if (!scrollElement) {
    return (
      <div className="vlive-violations-virtual" role="list" aria-label={label}>
        {items.map((item, i) => (
          <div key={getItemKey(i)} role="listitem">{renderItem(item)}</div>
        ))}
      </div>
    );
  }

  const totalSize = virtualizer.getTotalSize();
  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      className="vlive-violations-virtual"
      role="list"
      aria-label={label}
      style={{ position: 'relative', width: '100%', height: totalSize }}
    >
      {virtualItems.map((virtualRow) => {
        const item = items[virtualRow.index];
        if (!item) return null;
        return (
          <div
            key={virtualRow.key}
            data-index={virtualRow.index}
            ref={virtualizer.measureElement}
            role="listitem"
            aria-setsize={items.length}
            aria-posinset={virtualRow.index + 1}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualRow.start - scrollMargin}px)`,
            }}
          >
            {renderItem(item)}
          </div>
        );
      })}
    </div>
  );
}
