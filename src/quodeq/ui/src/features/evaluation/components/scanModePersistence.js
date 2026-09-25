/**
 * Persistence for ScanModeCards' "always clean scan" preference.
 *
 * Split out of ScanModeCards.jsx verbatim.
 */
import { readString, removeKey, writeString, STORAGE_FLAG_ON } from '../../../adapters/storage.js';

const STORAGE_KEY = 'quodeq.cleanScan.permanent';

export function readPermanent() {
  return readString(STORAGE_KEY) === STORAGE_FLAG_ON;
}

export function writePermanent(on) {
  if (on) writeString(STORAGE_KEY, STORAGE_FLAG_ON);
  else removeKey(STORAGE_KEY);
}
