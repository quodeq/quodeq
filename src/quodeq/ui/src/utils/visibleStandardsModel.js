/**
 * Pure migration-policy for `hydrateVisibleStandardIds` (visibleStandards.js).
 * Zero imports so it is node-testable without a DOM.
 */

export function sameIdSet(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length === 0 && b.length === 0) return true;
  const setA = new Set(a);
  const setB = new Set(b);
  if (setA.size !== setB.size) return false;
  for (const id of setA) {
    if (!setB.has(id)) return false;
  }
  return true;
}

/**
 * Decide what hydrateVisibleStandardIds should do with a resolved
 * getStandardsVisibility response, given the locally cached ids.
 *
 * Returns `{ kind: 'migrate', ids: cachedIds }` when the cache carries real
 * user intent worth pushing up to the server, or `{ kind: 'adopt', ids:
 * serverIds, markMigrated }` otherwise.
 *
 * Migrate iff: the server has no file yet (isDefault), migration hasn't
 * already happened once for this browser (alreadyMigrated), there IS a
 * cached selection (Array.isArray(cachedIds)), and that cached selection
 * actually differs from the ISO defaults (a cache that already equals the
 * defaults is nothing but the trailing residue of an earlier hydrate and
 * must not spawn a file with nothing but the defaults in it). Prefer the
 * server's own default set when the response carries one (additive
 * `serverDefaults`); the JS constant (`fallbackDefaults`) is only the
 * pre-hydration boot fallback for when the server hasn't answered yet.
 *
 * `markMigrated` on the adopt path mirrors the orchestrator's other
 * migration guard: once a project has its own real file (`!isDefault`), the
 * cache is now known to belong to a specific project's synced selection, so
 * it must never again be read as an unclaimed legacy value up for grabs by
 * the next project that happens to have no file yet.
 */
export function decideHydration({ serverIds, isDefault, serverDefaults, cachedIds, alreadyMigrated, fallbackDefaults }) {
  if (isDefault && !alreadyMigrated && Array.isArray(cachedIds)) {
    const isoDefaults = Array.isArray(serverDefaults) ? serverDefaults : fallbackDefaults;
    if (!sameIdSet(cachedIds, isoDefaults)) {
      return { kind: 'migrate', ids: cachedIds };
    }
  }
  return { kind: 'adopt', ids: serverIds, markMigrated: !isDefault };
}
