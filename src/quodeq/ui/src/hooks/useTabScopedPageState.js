import { useRef } from 'react';
import { readCachedState, resetCachedScope } from '../utils/pageStateCache.js';

/**
 * The page's cached state for `scope`, dropped first when `tabKey` changed
 * (a fresh click on the tab itself). Round-tripping through a detail view
 * keeps tabKey, so the cached state survives unmount and remount.
 *
 * `cache` is an optional injected page-state cache (see pageStateCache.js);
 * with none given this goes through the module's own free functions (the
 * shared default).
 */
export function useTabScopedPageState({ namespace, scope, tabKey, defaults, cache }) {
  const lastTabKeyRef = useRef(tabKey);
  const reset = cache ? cache.resetCachedScope : resetCachedScope;
  const read = cache ? cache.readCachedState : readCachedState;
  if (lastTabKeyRef.current !== tabKey) {
    reset(namespace, scope);
    lastTabKeyRef.current = tabKey;
  }
  return read(namespace, scope, defaults);
}
