import { useState, useEffect, startTransition } from 'react';

/**
 * False on the first commit, true from the next one, flipped inside a
 * transition so the first commit's frame reaches the screen before React
 * starts on whatever the flag gates, and so that render stays time-sliced.
 *
 * Use this directly when a page's expensive work is a hook (a memo that
 * builds a tree, a layout) rather than a subtree: feed the hook empty input
 * until ready. Prefer DeferredMount when the expensive part is a subtree.
 */
export function useDeferredReady() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    startTransition(() => setReady(true));
  }, []);
  return ready;
}

/**
 * Two-commit mount for heavy content. Commit 1 shows `fallback`, so a
 * navigation to the page paints something immediately; the children then
 * render in a transition, off the urgent path, and replace it.
 *
 * Only worth using where the children are expensive enough to hold the first
 * paint hostage — pages that fetch already get this shape for free from
 * their loading state.
 */
export default function DeferredMount({ fallback, children }) {
  const ready = useDeferredReady();
  return ready ? children : fallback;
}
