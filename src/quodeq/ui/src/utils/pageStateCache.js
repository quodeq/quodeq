/**
 * Module-scoped state cache for pages that unmount when the user drills
 * into a detail view.
 *
 * Problem: Map and Violations pages unmount when the user navigates to a
 * file or principle detail (the app's nav stack only renders the top
 * entry). Coming back remounts the page — useState/useRef defaults win,
 * and the prior navigation state (current path, active sub-tab, viz mode,
 * dimension filter) is lost.
 *
 * Fix: store the small slice of state that needs to survive unmount in a
 * Map keyed by a scope string (typically the selected project id). A
 * fresh click on the tab itself should still reset — call `resetScope()`
 * when `tabKey` changes.
 *
 * This is deliberately session-only and not persisted to storage — page
 * reloads start fresh, which matches the user's existing expectation.
 */

const STORES = new Map(); // namespace -> Map<scope, state object>

function storeFor(namespace) {
  let s = STORES.get(namespace);
  if (!s) {
    s = new Map();
    STORES.set(namespace, s);
  }
  return s;
}

export function readCachedState(namespace, scope, defaults) {
  const existing = storeFor(namespace).get(scope || '__global__');
  if (existing) return { ...defaults, ...existing };
  return { ...defaults };
}

export function writeCachedState(namespace, scope, patch) {
  const key = scope || '__global__';
  const store = storeFor(namespace);
  const prev = store.get(key) || {};
  store.set(key, { ...prev, ...patch });
}

export function resetCachedScope(namespace, scope) {
  storeFor(namespace).delete(scope || '__global__');
}
