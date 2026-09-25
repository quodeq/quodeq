/**
 * Scan-result model — a project's quick-scan summary (file/code/language/
 * branch counts). The raw API response (`ScanData` in `core/types/scan.py`,
 * served via `dataclasses.asdict` by `/scan` and `/projects/:id/scan`)
 * spells its fields snake_case.
 *
 * @typedef {Object} ScanSummary
 * @property {number}                totalFiles
 * @property {number}                codeFiles
 * @property {number}                untrackedFiles
 * @property {Object<string,number>} languages
 * @property {string[]}              branches
 * @property {string[]}              modules
 * @property {string}                scannedAt
 */

import { fromFieldSpec } from './fieldSpec.js';

/**
 * Field table for {@link createScanSummary}: output key -> [raw spelling(s), default].
 */
const SCAN_SUMMARY_FIELDS = {
  totalFiles:     [['totalFiles', 'total_files'], 0],
  codeFiles:      [['codeFiles', 'code_files'], 0],
  untrackedFiles: [['untrackedFiles', 'untracked_files'], 0],
  languages:      ['languages', () => ({})],
  branches:       ['branches', () => []],
  modules:        ['modules', () => []],
  scannedAt:      [['scannedAt', 'scanned_at'], ''],
};

/**
 * Create a canonical ScanSummary from a raw scan API response.
 *
 * @param {Object} raw
 * @returns {ScanSummary}
 */
export function createScanSummary(raw) {
  if (!raw || typeof raw !== 'object') return raw;
  return fromFieldSpec(raw, SCAN_SUMMARY_FIELDS);
}
