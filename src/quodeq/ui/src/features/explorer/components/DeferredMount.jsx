import { useState, useEffect, startTransition } from 'react';

/**
 * Two-commit mount for heavy, param-fed content (the principle / file detail
 * card lists). Commit 1 shows `fallback`, so a navigation to the page paints
 * something immediately; the children then render in a transition, off the
 * urgent path, and replace it.
 *
 * Only worth using where the children are expensive enough to hold the first
 * paint hostage — pages that fetch already get this shape for free from
 * their loading state.
 */
export default function DeferredMount({ fallback, children }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    // Transition, not a plain set: lets the fallback's frame reach the screen
    // before React starts the heavy render, and keeps that render time-sliced.
    startTransition(() => setReady(true));
  }, []);
  return ready ? children : fallback;
}
