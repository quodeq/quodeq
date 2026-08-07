import { useState } from 'react';
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
 */
export default function VirtualList({ items, scrollElement, estimateSize, getItemKey, renderItem, overscan = 6 }) {
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollElement,
    estimateSize,
    overscan,
    getItemKey,
  });

  if (!scrollElement) {
    return (
      <div className="vlive-violations-virtual">
        {items.map((item, i) => (
          <div key={getItemKey(i)}>{renderItem(item)}</div>
        ))}
      </div>
    );
  }

  const totalSize = virtualizer.getTotalSize();
  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div className="vlive-violations-virtual" style={{ position: 'relative', width: '100%', height: totalSize }}>
      {virtualItems.map((virtualRow) => {
        const item = items[virtualRow.index];
        if (!item) return null;
        return (
          <div
            key={virtualRow.key}
            data-index={virtualRow.index}
            ref={virtualizer.measureElement}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualRow.start}px)`,
            }}
          >
            {renderItem(item)}
          </div>
        );
      })}
    </div>
  );
}
