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

export function clampHeight(px) {
  return Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, px));
}

export function readStoredHeight(storage) {
  const raw = readString(HEIGHT_KEY, null, storage);
  const n = raw ? parseInt(raw, 10) : NaN;
  return Number.isFinite(n) ? clampHeight(n) : DEFAULT_HEIGHT;
}

export function writeStoredHeight(px, storage) {
  writeString(HEIGHT_KEY, px, storage);
}

export function useDrawerHeight() {
  const [height, setHeightState] = useState(() => readStoredHeight());
  const setHeight = useCallback((px) => {
    const next = clampHeight(px);
    setHeightState(next);
    writeStoredHeight(next);
  }, []);
  return { height, setHeight };
}
