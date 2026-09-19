import { useCallback, useEffect, useRef, useState } from 'react';
import { clampSidePaneWidth } from '../paneWidthMath.js';
import { useDragLifecycle } from './useDragLifecycle.js';

/**
 * Drag-to-resize for the side pane's outer edge, writing the width to the
 * `--side-pane-width` custom property as the pointer moves.
 *
 * Also owns the plumbing the inner divider drag shares: the container ref it
 * reaches into, the `data-pane-resizing` flag setter, and the active-drag
 * cleanup ref both drags register into so unmount always runs whichever
 * cleanup is live.
 *
 * While a drag is live it sets `data-pane-resizing` on the document root,
 * which CSS uses to suppress the column-width transition — without it the
 * pane edge lags the cursor and the main column reflows on every move. Any
 * drag still active at unmount is cleaned up.
 */
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

  const beginDrag = useDragLifecycle({ setResizingFlag, activeDragCleanupRef });

  const [isDragging, setIsDragging] = useState(false);
  const onOuterDividerPointerDown = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = paneWidth;
    const viewport = window.innerWidth;

    let pendingNext = startWidth;
    const apply = () => {
      document.documentElement.style.setProperty('--side-pane-width', `${pendingNext}px`);
    };
    setIsDragging(true);
    beginDrag({
      cursor: 'col-resize',
      onMove: (ev) => {
        pendingNext = clampSidePaneWidth(startWidth + (startX - ev.clientX), viewport);
      },
      onFrame: apply,
      onEnd: (ev) => {
        const finalWidth = clampSidePaneWidth(startWidth + (startX - ev.clientX), window.innerWidth);
        // Write final value to the var immediately so the column doesn't
        // jump on the next React commit; setPaneWidth then persists state.
        document.documentElement.style.setProperty('--side-pane-width', `${finalWidth}px`);
        setPaneWidth(finalWidth);
        setIsDragging(false);
      },
    });
  }, [paneWidth, setPaneWidth, beginDrag]);

  return { containerRef, setResizingFlag, activeDragCleanupRef, isDragging, onOuterDividerPointerDown };
}
