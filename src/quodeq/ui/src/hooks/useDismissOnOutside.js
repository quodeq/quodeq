import { useEffect } from 'react';
import { KEY } from '../vocab/keyboard.js';

/**
 * Closes an open popover on a press outside `rootRef` or on Escape. The
 * listeners exist only while `open` is true.
 * @param {boolean} open
 * @param {{current: Element|null}} rootRef - the popover's trigger and menu wrapper
 * @param {() => void} close
 */
export function useDismissOnOutside(open, rootRef, close) {
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) close(); };
    const onKey = (e) => { if (e.key === KEY.ESCAPE) close(); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, rootRef, close]);
}
