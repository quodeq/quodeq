import { useCallback, useRef, useState } from 'react';
import { useDismissOnOutside } from '../../../hooks/useDismissOnOutside.js';

/**
 * A small popup menu's state: open or closed, closed by a click outside its
 * root, and `pick(fn)` for an item (closes, then runs the action). Shared by
 * the Repositories header's `more ▾` and the sync strip's `⋯`.
 * @returns {{ open: boolean, rootRef: import('react').RefObject, toggle: () => void, pick: (fn?: Function) => () => void }}
 */
export function useMenuToggle() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  useDismissOnOutside(open, rootRef, close);
  const toggle = useCallback(() => setOpen((o) => !o), []);
  const pick = (fn) => () => { close(); fn?.(); };
  return { open, rootRef, toggle, pick };
}
