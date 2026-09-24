import { useCallback } from 'react';
import { POINTER_EVENT } from '../../../vocab/pointerEvent.js';

/**
 * The pointer-drag lifecycle the side pane's two resizers share: take over
 * the body cursor and text selection, follow the rest of the gesture on the
 * window, coalesce pointermove into one DOM write per animation frame, and
 * put everything back on pointerup.
 *
 * Returns `beginDrag({ cursor, onMove, onFrame, onEnd })`, which starts a
 * gesture and returns its cleanup. The same cleanup is published through
 * `activeDragCleanupRef` so an unmount mid-drag can tear the gesture down.
 *
 * `onMove(event)` runs on every pointermove and should only do arithmetic;
 * `onFrame()` does the DOM write and runs at most once per frame, because
 * pointermove can fire 100+ times/sec on a 120Hz trackpad; `onEnd(event)`
 * runs on pointerup, before the teardown.
 */
export function useDragLifecycle({ setResizingFlag, activeDragCleanupRef }) {
  return useCallback(({ cursor, onMove, onFrame, onEnd }) => {
    setResizingFlag(true);
    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;
    document.body.style.cursor = cursor;
    document.body.style.userSelect = 'none';

    let rafId = null;
    const frame = () => {
      rafId = null;
      onFrame();
    };
    const handleMove = (ev) => {
      onMove(ev);
      if (rafId == null) rafId = requestAnimationFrame(frame);
    };
    const cleanup = () => {
      if (rafId != null) cancelAnimationFrame(rafId);
      setResizingFlag(false);
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      window.removeEventListener(POINTER_EVENT.MOVE, handleMove);
      window.removeEventListener(POINTER_EVENT.UP, handleUp);
      activeDragCleanupRef.current = null;
    };
    const handleUp = (ev) => {
      onEnd(ev);
      cleanup();
    };

    window.addEventListener(POINTER_EVENT.MOVE, handleMove);
    window.addEventListener(POINTER_EVENT.UP, handleUp);
    activeDragCleanupRef.current = cleanup;
    return cleanup;
  }, [setResizingFlag, activeDragCleanupRef]);
}
