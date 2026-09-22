/**
 * Persistence for ScanModeCards' "always clean scan" preference.
 *
 * Split out of ScanModeCards.jsx verbatim.
 */
import { readString, removeKey, writeString } from '../../../adapters/storage.js';

const STORAGE_KEY = 'quodeq.cleanScan.permanent';

export function readPermanent() {
  return readString(STORAGE_KEY) === '1';
}

export function writePermanent(on) {
  if (on) writeString(STORAGE_KEY, '1');
  else removeKey(STORAGE_KEY);
}
