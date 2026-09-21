/**
 * The assistant drawer's persisted, clamped height. Moved off hand-rolled
 * localStorage try/catch onto adapters/storage.js.
 */
import { useCallback, useState } from 'react';
import { readString, writeString } from '../../adapters/storage.js';

export const HEIGHT_KEY = 'cc-assistant-drawer-height';
export const DEFAULT_HEIGHT = 320;
export const MIN_HEIGHT = 160;
export const MAX_HEIGHT = 640;

/** Holds a drawer height inside the resize range. */
export function clampHeight(px) {
  return Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, px));
}

/**
 * The persisted drawer height, clamped. Anything unparseable (absent key,
 * private browsing, a hand-edited value) falls back to DEFAULT_HEIGHT.
 * @param {Storage} [storage] - injectable for tests.
 * @returns {number} height in px.
 */
export function readStoredHeight(storage) {
  const raw = readString(HEIGHT_KEY, null, storage);
  const n = raw ? parseInt(raw, 10) : NaN;
  return Number.isFinite(n) ? clampHeight(n) : DEFAULT_HEIGHT;
}

/** Persist a drawer height. A storage failure is swallowed by the adapter. */
export function writeStoredHeight(px, storage) {
  writeString(HEIGHT_KEY, px, storage);
}

/**
 * The assistant drawer's height, seeded from storage and persisted on every
 * change so a reopen keeps the size the user dragged to.
 * @returns {{height: number, setHeight: (px: number) => void}} `setHeight`
 *   clamps before storing, so a drag past the limits is pinned, not rejected.
 */
export function useDrawerHeight() {
  const [height, setHeightState] = useState(() => readStoredHeight());
  const setHeight = useCallback((px) => {
    const next = clampHeight(px);
    setHeightState(next);
    writeStoredHeight(next);
  }, []);
  return { height, setHeight };
}
