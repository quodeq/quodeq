/**
 * useAppScrollParent — locate the app's existing scroll container so
 * descendant components (Virtuoso lists, etc.) can reuse it instead of
 * creating their own nested scrollbar.
 *
 * Returns `[probeRef, scrollParent, ready]`:
 *
 * - `probeRef` — attach to a trivial DOM node (a hidden <span>) that's a
 *   descendant of the scroll container you want to find.
 * - `scrollParent` — the nearest ancestor of the probe node whose computed
 *   `overflow-y` is `auto` or `scroll` AND actually overflows. `null` until
 *   layout has committed; after that, either the DOM element or `null` if
 *   nothing scrollable exists above (use `useWindowScroll` as a fallback).
 * - `ready` — `false` on first render, `true` after the layout effect has
 *   run and `scrollParent` has been resolved. Gate the list render on this
 *   to avoid Virtuoso mounting with the wrong scroll mode and then needing
 *   to swap — that transition is where the "rows don't appear until
 *   scroll" regression came from.
 *
 * Detection runs in `useLayoutEffect` so it commits synchronously before
 * the browser paints, keeping the pre-ready render imperceptible.
 */
import { useLayoutEffect, useRef, useState } from 'react';

function findScrollParent(el) {
  if (typeof window === 'undefined' || !el) return null;
  let node = el.parentElement;
  while (node && node !== document.body && node !== document.documentElement) {
    const style = window.getComputedStyle(node);
    if ((style.overflowY === 'auto' || style.overflowY === 'scroll')
        && node.scrollHeight > node.clientHeight) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

export function useAppScrollParent() {
  const probeRef = useRef(null);
  const [scrollParent, setScrollParent] = useState(null);
  const [ready, setReady] = useState(false);
  useLayoutEffect(() => {
    setScrollParent(findScrollParent(probeRef.current));
    setReady(true);
  }, []);
  return [probeRef, scrollParent, ready];
}
