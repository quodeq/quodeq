import { useCallback, useState } from 'react';
import { clampSidePaneWidth } from '../paneWidthMath.js';
import { useDragLifecycle } from './useDragLifecycle.js';

// The pane's width lives in a CSS custom property during a drag: writing it
// directly keeps the column following the cursor without a React commit per
// frame. Written once per frame while dragging, then once more on release.
function writePaneWidthVar(px) {
  document.documentElement.style.setProperty('--side-pane-width', `${px}px`);
}

/**
 * Drag-to-resize for the side pane's outer edge, writing the width to the
 * `--side-pane-width` custom property as the pointer moves. The shared
 * resizing flag and cleanup slot come from usePaneDragPlumbing, which the
 * inner divider drag reads too.
 *
 * @param {object} args
 * @param {number} args.paneWidth - the committed width a drag starts from.
 * @param {(px: number) => void} args.setPaneWidth - commits the released width.
 * @param {(on: boolean) => void} args.setResizingFlag
 * @param {object} args.activeDragCleanupRef
 * @returns {{isDragging: boolean, onOuterDividerPointerDown: Function}}
 */
export function useOuterPaneDrag({ paneWidth, setPaneWidth, setResizingFlag, activeDragCleanupRef }) {
  const beginDrag = useDragLifecycle({ setResizingFlag, activeDragCleanupRef });

  const [isDragging, setIsDragging] = useState(false);
  const onOuterDividerPointerDown = useCallback((e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = paneWidth;
    // The viewport is captured for the move (one read per drag, not per
    // frame) and re-read on release, so a resize mid-drag still commits a
    // width that fits.
    const viewport = window.innerWidth;
    const widthAt = (ev, viewportWidth) => clampSidePaneWidth(startWidth + (startX - ev.clientX), viewportWidth);

    let pendingNext = startWidth;
    setIsDragging(true);
    beginDrag({
      cursor: 'col-resize',
      onMove: (ev) => {
        pendingNext = widthAt(ev, viewport);
      },
      onFrame: () => writePaneWidthVar(pendingNext),
      onEnd: (ev) => {
        const finalWidth = widthAt(ev, window.innerWidth);
        // Write final value to the var immediately so the column doesn't
        // jump on the next React commit; setPaneWidth then persists state.
        writePaneWidthVar(finalWidth);
        setPaneWidth(finalWidth);
        setIsDragging(false);
      },
    });
  }, [paneWidth, setPaneWidth, beginDrag]);

  return { isDragging, onOuterDividerPointerDown };
}
