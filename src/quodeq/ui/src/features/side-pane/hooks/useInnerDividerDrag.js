import { useCallback, useEffect, useState } from 'react';

const MIN_WINDOW_RATIO = 0.1;

/**
 * SidePane.jsx's internal between-window resizer, plus the per-resizer
 * ratios state it (and the render's weights calc) reads. Extracted verbatim
 * from SidePane.jsx; the pointer-down body was split into the helpers below
 * purely to fit the size ratchet's per-function line cap — same logic, same
 * closures.
 *
 * Mutates the two adjacent slot elements' inline flex grow factors directly
 * during the drag (no setState — same trick as the outer drag with
 * --side-pane-width) so the markdown bodies don't re-render every pointer
 * move. Commits the final ratio to React state on release.
 */
function beginInnerDragUI({ setResizingFlag }) {
  setResizingFlag(true);
  const prevCursor = document.body.style.cursor;
  const prevSelect = document.body.style.userSelect;
  document.body.style.cursor = 'row-resize';
  document.body.style.userSelect = 'none';
  return { prevCursor, prevSelect };
}

function makeInnerDragHandlers({
  aEl, bEl, startY, startRatio, span, combinedFlex, prevCursor, prevSelect,
  setResizingFlag, setRatios, index, activeDragCleanupRef,
}) {
  let pendingRatio = startRatio;
  let rafId = null;
  const apply = () => {
    rafId = null;
    aEl.style.flex = `${combinedFlex * pendingRatio} 1 0`;
    bEl.style.flex = `${combinedFlex * (1 - pendingRatio)} 1 0`;
  };
  const onMove = (ev) => {
    const delta = ev.clientY - startY;
    pendingRatio = Math.min(1 - MIN_WINDOW_RATIO, Math.max(MIN_WINDOW_RATIO, startRatio + delta / span));
    if (rafId == null) rafId = requestAnimationFrame(apply);
  };
  const cleanup = () => {
    if (rafId != null) cancelAnimationFrame(rafId);
    setResizingFlag(false);
    document.body.style.cursor = prevCursor;
    document.body.style.userSelect = prevSelect;
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    activeDragCleanupRef.current = null;
  };
  const onUp = () => {
    apply();
    setRatios((prev) => {
      const out = [...prev];
      out[index] = pendingRatio;
      return out;
    });
    cleanup();
  };
  return { onMove, onUp, cleanup };
}

export function useInnerDividerDrag({ windowCount, containerRef, setResizingFlag, activeDragCleanupRef }) {
  // Per-resizer ratios: ratios[i] in [0,1] is the share of (weights[i] + weights[i+1])
  // that goes to weights[i]. Reset whenever the window count changes (structural reset).
  const [ratios, setRatios] = useState(() => Array(Math.max(0, windowCount - 1)).fill(0.5));
  useEffect(() => {
    setRatios(Array(Math.max(0, windowCount - 1)).fill(0.5));
  }, [windowCount]);

  const onInnerDividerPointerDown = useCallback((index) => (e) => {
    e.preventDefault();
    const container = containerRef.current;
    if (!container) return;
    const slots = container.querySelectorAll('.side-pane-window-slot');
    const aEl = slots[index];
    const bEl = slots[index + 1];
    if (!aEl || !bEl) return;
    const startY = e.clientY;
    const startRatio = ratios[index] ?? 0.5;
    const span = aEl.offsetHeight + bEl.offsetHeight;
    if (span <= 0) return;
    // Combined weight of these two slots stays constant during this drag —
    // we just split it differently. Capture it once.
    const aStartFlex = parseFloat(aEl.style.flexGrow) || 1;
    const bStartFlex = parseFloat(bEl.style.flexGrow) || 1;
    const combinedFlex = aStartFlex + bStartFlex;
    const { prevCursor, prevSelect } = beginInnerDragUI({ setResizingFlag });
    const { onMove, onUp, cleanup } = makeInnerDragHandlers({
      aEl, bEl, startY, startRatio, span, combinedFlex, prevCursor, prevSelect,
      setResizingFlag, setRatios, index, activeDragCleanupRef,
    });
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    activeDragCleanupRef.current = cleanup;
  }, [ratios, setResizingFlag]); // eslint-disable-line react-hooks/exhaustive-deps

  return { ratios, setRatios, onInnerDividerPointerDown };
}

export { MIN_WINDOW_RATIO };
