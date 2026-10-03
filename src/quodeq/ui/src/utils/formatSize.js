import { t } from '../strings/index.js';

const BYTES_PER_KB = 1024;
const BYTES_PER_MB = BYTES_PER_KB * BYTES_PER_KB;
const MB_DECIMALS = 1;

/**
 * A byte count as display text: one decimal in MB from 1 MB up ("12.0 MB"),
 * whole KB below it ("2 KB", never "0 KB" for a non-empty count).
 * @param {number|null|undefined} bytes
 * @returns {string|null} null when there is no count to show yet (0 included)
 */
export function formatSize(bytes) {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes <= 0) return null;
  if (bytes >= BYTES_PER_MB) return t('common.sizeMb', { size: (bytes / BYTES_PER_MB).toFixed(MB_DECIMALS) });
  return t('common.sizeKb', { size: Math.max(1, Math.round(bytes / BYTES_PER_KB)) });
}
