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

const GLOBAL_SCOPE_KEY = '__global__'; // key used when no scope (project id) is given

// Map iteration is insertion-ordered, so re-inserting on every touch keeps
// the least recently used scope at the front for eviction.
function touch(store, key, value) {
  store.delete(key);
  store.set(key, value);
}

/**
 * Build an independent page-state cache: its own namespace -> scope map,
 * closing over its own eviction cap. `maxScopes` decouples the cap from
 * MAX_SCOPES_PER_NAMESPACE for tests; production code shares one default
 * instance (see `defaultPageStateCache` below).
 */
export function createPageStateCache({ maxScopes = MAX_SCOPES_PER_NAMESPACE } = {}) {
  const STORES = new Map(); // namespace -> Map<scope, state object>, oldest first

  function storeFor(namespace) {
    let s = STORES.get(namespace);
    if (!s) {
      s = new Map();
      STORES.set(namespace, s);
    }
    return s;
  }

  // The scope's surviving state merged over `defaults`, and a copy of
  // `defaults` alone when the scope has nothing cached. Reading also marks
  // the scope as recently used.
  function read(namespace, scope, defaults) {
    const key = scope || GLOBAL_SCOPE_KEY;
    const store = storeFor(namespace);
    const existing = store.get(key);
    if (!existing) return { ...defaults };
    touch(store, key, existing);
    return { ...defaults, ...existing };
  }

  // Merges `patch` into the scope's cached state, evicting the least
  // recently used scope once the namespace passes maxScopes.
  function write(namespace, scope, patch) {
    const key = scope || GLOBAL_SCOPE_KEY;
    const store = storeFor(namespace);
    const prev = store.get(key) || {};
    touch(store, key, { ...prev, ...patch });
    if (store.size > maxScopes) store.delete(store.keys().next().value);
  }

  // Drops one scope, so the next read falls back to the defaults. This is
  // the "user clicked the tab itself" reset.
  function resetScope(namespace, scope) {
    storeFor(namespace).delete(scope || GLOBAL_SCOPE_KEY);
  }

  // Drop every namespace and scope.
  function clearAll() {
    STORES.clear();
  }

  return {
    readCachedState: read,
    writeCachedState: write,
    resetCachedScope: resetScope,
    clearAllCachedState: clearAll,
  };
}

/** The app-wide page-state cache every production import shares. */
export const defaultPageStateCache = createPageStateCache();

/**
 * The scope's surviving state merged over `defaults`, and a copy of
 * `defaults` alone when the scope has nothing cached. Reading also marks the
 * scope as recently used. Delegates to defaultPageStateCache; call
 * createPageStateCache() for an independent cache.
 */
export function readCachedState(namespace, scope, defaults) {
  return defaultPageStateCache.readCachedState(namespace, scope, defaults);
}

/**
 * Merges `patch` into the scope's cached state, evicting the least recently
 * used scope once the namespace passes MAX_SCOPES_PER_NAMESPACE. Delegates
 * to defaultPageStateCache.
 */
export function writeCachedState(namespace, scope, patch) {
  return defaultPageStateCache.writeCachedState(namespace, scope, patch);
}

/**
 * Drops one scope, so the next read falls back to the defaults. This is the
 * "user clicked the tab itself" reset. Delegates to defaultPageStateCache.
 */
export function resetCachedScope(namespace, scope) {
  return defaultPageStateCache.resetCachedScope(namespace, scope);
}

/**
 * Drop every namespace and scope.
 *
 * Test-isolation hook: the default cache is module-scoped, so without this a
 * page's cached state leaks into the next test in the same process.
 * Production code uses `resetCachedScope` for the narrower "user clicked the
 * tab" reset.
 */
export function clearAllCachedState() {
  return defaultPageStateCache.clearAllCachedState();
}
