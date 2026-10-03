import { useEffect, useMemo, useState } from 'react';
import { resolvePackLayout } from './layoutCache.js';

/** The pack layout for `node` in `viewMode`. Synchronous when cached or
 * small; for large trees it returns no circles until the worker replies,
 * then re-renders with them. A reply for a node the view has since left is
 * ignored. */
export function usePackLayout(node, viewMode) {
  const layout = useMemo(() => resolvePackLayout(node, viewMode), [node, viewMode]);
  const [settled, setSettled] = useState(null);

  useEffect(() => {
    if (!layout.pending) return undefined;
    let live = true;
    void layout.promise.then((done) => { if (live) setSettled({ node, viewMode, layout: done }); });
    return () => { live = false; };
  }, [layout, node, viewMode]);

  if (!layout.pending) return layout;
  if (settled && settled.node === node && settled.viewMode === viewMode) return settled.layout;
  return layout;
}
