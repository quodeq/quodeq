import { useCallback, useEffect, useState } from 'react';
import { useDragLifecycle } from './useDragLifecycle.js';

const MIN_WINDOW_RATIO = 0.1;
// Default 50/50 split between two adjacent stacked windows, before any drag
// or keyboard resize has run.
export const DEFAULT_SPLIT_RATIO = 0.5;

/**
 * Drag-to-resize between stacked side-pane windows.
 *
 * `ratios[i]` is how much of the combined height of windows i and i+1 goes to
 * i; the pair's total is held constant through a drag, so resizing one seam
 * never disturbs the others. The ratios reset whenever the window count
 * changes. The active drag's cleanup is published through
 * `activeDragCleanupRef` so the owner can tear down leaked listeners.
 *
 * Mutates the two adjacent slot elements' inline flex grow factors directly
 * during the drag (no setState — same trick as the outer drag with
 * --side-pane-width) so the markdown bodies don't re-render every pointer
 * move. Commits the final ratio to React state on release.
 */
export function useInnerDividerDrag({ windowCount, containerRef, setResizingFlag, activeDragCleanupRef }) {
  // Per-resizer ratios: ratios[i] in [0,1] is the share of (weights[i] + weights[i+1])
  // that goes to weights[i]. Reset whenever the window count changes (structural reset).
  const [ratios, setRatios] = useState(() => Array(Math.max(0, windowCount - 1)).fill(DEFAULT_SPLIT_RATIO));
  useEffect(() => {
    setRatios(Array(Math.max(0, windowCount - 1)).fill(DEFAULT_SPLIT_RATIO));
  }, [windowCount]);

  const beginDrag = useDragLifecycle({ setResizingFlag, activeDragCleanupRef });

  const onInnerDividerPointerDown = useCallback((index) => (e) => {
    e.preventDefault();
    const container = containerRef.current;
    if (!container) return;
    const slots = container.querySelectorAll('.side-pane-window-slot');
    const aEl = slots[index];
    const bEl = slots[index + 1];
    if (!aEl || !bEl) return;
    const startY = e.clientY;
    const startRatio = ratios[index] ?? DEFAULT_SPLIT_RATIO;
    const span = aEl.offsetHeight + bEl.offsetHeight;
    if (span <= 0) return;
    // Combined weight of these two slots stays constant during this drag —
    // we just split it differently. Capture it once.
    const aStartFlex = parseFloat(aEl.style.flexGrow) || 1;
    const bStartFlex = parseFloat(bEl.style.flexGrow) || 1;
    const combinedFlex = aStartFlex + bStartFlex;

    let pendingRatio = startRatio;
    const apply = () => {
      aEl.style.flex = `${combinedFlex * pendingRatio} 1 0`;
      bEl.style.flex = `${combinedFlex * (1 - pendingRatio)} 1 0`;
    };
    beginDrag({
      cursor: 'row-resize',
      onMove: (ev) => {
        const delta = ev.clientY - startY;
        pendingRatio = Math.min(1 - MIN_WINDOW_RATIO, Math.max(MIN_WINDOW_RATIO, startRatio + delta / span));
      },
      onFrame: apply,
      onEnd: () => {
        apply();
        setRatios((prev) => {
          const out = [...prev];
          out[index] = pendingRatio;
          return out;
        });
      },
    });
  }, [ratios, beginDrag]); // eslint-disable-line react-hooks/exhaustive-deps

  return { ratios, setRatios, onInnerDividerPointerDown };
}

export { MIN_WINDOW_RATIO };
