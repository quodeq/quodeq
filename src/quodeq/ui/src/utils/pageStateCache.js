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
 *
 * Each namespace keeps at most MAX_SCOPES_PER_NAMESPACE scopes, least
 * recently used first out, so a long session hopping across many projects
 * cannot grow the cache without bound.
 */

// Scopes are project ids, so this is "how many projects' page state to keep".
export const MAX_SCOPES_PER_NAMESPACE = 50;

const STORES = new Map(); // namespace -> Map<scope, state object>, oldest first

function storeFor(namespace) {
  let s = STORES.get(namespace);
  if (!s) {
    s = new Map();
    STORES.set(namespace, s);
  }
  return s;
}

// Map iteration is insertion-ordered, so re-inserting on every touch keeps
// the least recently used scope at the front for eviction.
function touch(store, key, value) {
  store.delete(key);
  store.set(key, value);
}

export function readCachedState(namespace, scope, defaults) {
  const key = scope || '__global__';
  const store = storeFor(namespace);
  const existing = store.get(key);
  if (!existing) return { ...defaults };
  touch(store, key, existing);
  return { ...defaults, ...existing };
}

export function writeCachedState(namespace, scope, patch) {
  const key = scope || '__global__';
  const store = storeFor(namespace);
  const prev = store.get(key) || {};
  touch(store, key, { ...prev, ...patch });
  if (store.size > MAX_SCOPES_PER_NAMESPACE) store.delete(store.keys().next().value);
}

export function resetCachedScope(namespace, scope) {
  storeFor(namespace).delete(scope || '__global__');
}

/**
 * Drop every namespace and scope.
 *
 * Test-isolation hook: the store is module-scoped, so without this a page's
 * cached state leaks into the next test in the same process. Production code
 * uses `resetCachedScope` for the narrower "user clicked the tab" reset.
 */
export function clearAllCachedState() {
  STORES.clear();
}
