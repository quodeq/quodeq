/**
 * Persistence for the Compare tab's project-scope selection.
 *
 * Kept out of compareModel.js on purpose: that module's builders are plain
 * data-in/data-out (see its docstring — "nothing here fetches"), and
 * storage access is a side effect the pure view-model layer stays clear of.
 */
import { readJSON, removeKey, writeJSON } from '../../adapters/storage.js';

export const SCOPE_STORAGE_KEY = 'quodeq.compare.scope';

/**
 * The saved scope (array of project ids), or null when nothing valid was
 * stored. null means "everything" (including projects added later).
 */
export function readStoredScope(storage) {
  const ids = readJSON(SCOPE_STORAGE_KEY, null, storage);
  return Array.isArray(ids) ? ids : null;
}

/** Persist the scope; `null` clears it (falls back to "everything"). */
export function storeScope(ids, storage) {
  if (ids == null) removeKey(SCOPE_STORAGE_KEY, storage);
  else writeJSON(SCOPE_STORAGE_KEY, ids, storage);
}
