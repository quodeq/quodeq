/**
 * Browser-storage adapter — the single place the UI touches `localStorage`.
 *
 * Every call site used to re-implement the same guard: a try/catch around
 * `getItem`/`setItem` (private mode and quota errors throw), plus a
 * `JSON.parse` fallback for structured values. That guard is here now, so
 * components and hooks state *what* they persist, not *how*.
 *
 * `storage` stays injectable with a `localStorage` default, matching the
 * pattern already used across the UI: tests pass a plain in-memory object
 * instead of leaning on a jsdom global.
 */

/** Resolve the backend, tolerating a missing/blocked `localStorage`. */
function backend(storage) {
  if (storage !== undefined) return storage;
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch (err) {
    console.warn('[storage] localStorage access blocked:', err); // cookies/storage blocked
    return null;
  }
}

/** Read a raw string. Returns `fallback` when absent or unreadable. */
export function readString(key, fallback = null, storage) {
  const s = backend(storage);
  if (!s) return fallback;
  try {
    const raw = s.getItem(key);
    return raw === null ? fallback : raw;
  } catch (err) {
    console.warn(`[storage] could not read "${key}":`, err);
    return fallback;
  }
}

/** Persist a raw string. Returns false when storage rejected the write. */
export function writeString(key, value, storage) {
  const s = backend(storage);
  if (!s) return false;
  try {
    s.setItem(key, String(value));
    return true;
  } catch (err) {
    console.warn(`[storage] could not write "${key}" (private mode or quota exceeded):`, err);
    return false; // non-fatal by design
  }
}

/** Read and parse JSON. Returns `fallback` when absent, unreadable or malformed. */
export function readJSON(key, fallback = null, storage) {
  const raw = readString(key, null, storage);
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw);
  } catch (err) {
    console.warn(`[storage] could not parse JSON for "${key}":`, err);
    return fallback;
  }
}

/** Serialize and persist JSON. Returns false when it could not be stored. */
export function writeJSON(key, value, storage) {
  let raw;
  try {
    raw = JSON.stringify(value);
  } catch (err) {
    console.warn('[storage] could not serialize value to JSON (cyclic or unserializable):', err);
    return false;
  }
  if (raw === undefined) return false;
  return writeString(key, raw, storage);
}

/** Remove a key. Never throws. */
export function removeKey(key, storage) {
  const s = backend(storage);
  if (!s) return;
  try {
    s.removeItem(key);
  } catch (err) {
    console.warn(`[storage] could not remove "${key}":`, err); // nothing to clean up
  }
}
