import { apiErrorMessage } from '../strings/apiErrors.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';

/**
 * The connect job's failure as display text, or null unless its slot is in
 * ERROR. The connect runs in the background, so its failure arrives through
 * the status's connect slot rather than as a rejection of the PUT.
 * @param {Object|undefined} connect - the status's connect slot
 * @param {string} fallbackKey - string key used when the code has no mapped copy
 * @returns {string|null}
 */
export function connectSlotError(connect, fallbackKey) {
  if (connect?.phase !== SYNC_PHASE.ERROR) return null;
  return apiErrorMessage({ code: connect.code, message: connect.error }, fallbackKey);
}
