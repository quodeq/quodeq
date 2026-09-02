import { useCallback, useEffect, useRef, useState } from 'react';
import { clampSidePaneWidth } from '../paneWidthMath.js';

/**
 * SidePane.jsx's outer pane (left-edge) drag — resizes the whole dock width
 * — plus the shared drag plumbing (the container ref the inner divider drag
 * also reaches into, the data-pane-resizing flag setter, and the
 * active-drag cleanup ref both drags register into so unmount always runs
 * whichever cleanup is live). Extracted verbatim from SidePane.jsx; the
 * pointer-down body was split into the two helpers below purely to fit the
 * size ratchet's per-function line cap — same logic, same closures.
 *
 * pointermove can fire 100+ times/sec on a 120Hz trackpad. Coalesce
 * multiple events into one CSS-var write per frame via rAF — same pattern
 * the inner divider uses for its flex writes.
 */
function beginOuterDragUI({ setResizingFlag, setIsDragging }) {
  setIsDragging(true);
  setResizingFlag(true);
  const prevCursor = document.body.style.cursor;
  const prevSelect = document.body.style.userSelect;
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  return { prevCursor, prevSelect };
}

function makeOuterDragHandlers({
  startX, startWidth, viewport, prevCursor, prevSelect, setResizingFlag, setIsDragging, setPaneWidth, activeDragCleanupRef,
}) {
  let pendingNext = startWidth;
  let rafId = null;
  const apply = () => {
    rafId = null;
    document.documentElement.style.setProperty('--side-pane-width', `${pendingNext}px`);
  };
  const onMove = (ev) => {
    const delta = startX - ev.clientX;
    pendingNext = clampSidePaneWidth(startWidth + delta, viewport);
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
  const onUp = (ev) => {
    const delta = startX - ev.clientX;
    const finalWidth = clampSidePaneWidth(startWidth + delta, window.innerWidth);
    // Write final value to the var immediately so the column doesn't
    // jump on the next React commit; setPaneWidth then persists state.
    document.documentElement.style.setProperty('--side-pane-width', `${finalWidth}px`);
    setPaneWidth(finalWidth);
    setIsDragging(false);
    cleanup();
  };
  return { onMove, onUp, cleanup };
}

export function useOuterPaneDrag({ paneWidth, setPaneWidth }) {
  // While dragging either divider, set data-pane-resizing on the document
  // root. The flag is read by a CSS rule on .app-shell__body that suppresses
  // its `transition: grid-template-columns 220ms ease` — without that, every
  // pointermove kicks off a fresh 220ms animation of the column width, so
  // the pane edge lags the cursor and the heavy main column reflows mid-
  // animation many times per drag step.
  const containerRef = useRef(null);
  const setResizingFlag = useCallback((on) => {
    const root = document.documentElement;
    if (on) root.dataset.paneResizing = 'true';
    else delete root.dataset.paneResizing;
  }, []);

  // Holds the cleanup function for the active drag, if any.
  // Set on pointer-down, cleared on pointer-up or unmount.
  const activeDragCleanupRef = useRef(null);

  // Run any active drag cleanup on unmount to remove leaked window listeners.
  useEffect(() => {
    return () => { activeDragCleanupRef.current?.(); };
  }, []);

  const [isDragging, setIsDragging] = useState(false);
  const onOuterDividerPointerDown = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = paneWidth;
    const viewport = window.innerWidth;
    const { prevCursor, prevSelect } = beginOuterDragUI({ setResizingFlag, setIsDragging });
    const { onMove, onUp, cleanup } = makeOuterDragHandlers({
      startX, startWidth, viewport, prevCursor, prevSelect, setResizingFlag, setIsDragging, setPaneWidth, activeDragCleanupRef,
    });
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    activeDragCleanupRef.current = cleanup;
  }, [paneWidth, setPaneWidth, setResizingFlag]);

  return { containerRef, setResizingFlag, activeDragCleanupRef, isDragging, onOuterDividerPointerDown };
}
