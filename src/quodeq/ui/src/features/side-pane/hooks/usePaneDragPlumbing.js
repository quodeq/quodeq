import { useCallback, useEffect, useRef } from 'react';

/**
 * The state both side-pane drags share, owned by neither of them: the pane
 * container they measure against, the `data-pane-resizing` flag, and the
 * cleanup slot whichever drag is live registers into.
 *
 * While a drag is live the flag sits on the document root, where a CSS rule
 * on `.app-shell__body` reads it to suppress `transition:
 * grid-template-columns 220ms ease`. Without that, every pointermove starts a
 * fresh 220ms animation of the column width, so the pane edge lags the cursor
 * and the heavy main column reflows many times per drag step.
 *
 * @returns {{containerRef: object, setResizingFlag: (on: boolean) => void,
 *   activeDragCleanupRef: object}} `activeDragCleanupRef.current` is called on
 *   unmount, so a drag interrupted by one leaves no window listeners behind.
 */
export function usePaneDragPlumbing() {
  const containerRef = useRef(null);

  const setResizingFlag = useCallback((on) => {
    const root = document.documentElement;
    if (on) root.dataset.paneResizing = 'true';
    else delete root.dataset.paneResizing;
  }, []);

  // Set on pointer-down by whichever drag started, cleared on pointer-up.
  const activeDragCleanupRef = useRef(null);

  useEffect(() => {
    return () => { activeDragCleanupRef.current?.(); };
  }, []);

  return { containerRef, setResizingFlag, activeDragCleanupRef };
}
