/**
 * Update notifications API — app version check, dismiss, and auto-check
 * settings.
 */

import { request } from './request.js';

// One endpoint carries every persisted update preference (auto-check, the
// one-time disclosure), so both writers post to the same path.
const SETTINGS_PATH = '/update/settings';

/**
 * The cached update state (current version, any available release, whether
 * auto-check is on).
 */
export function getUpdateStatus() {
  return request('/update/status');
}

/**
 * Forces a fresh upstream check instead of reading the cached status.
 */
export function checkForUpdates() {
  return request('/update/check', { method: 'POST' });
}

/**
 * Silences the notice for one version; a later release notifies again.
 * @param {string} version - the release being dismissed, not the running one.
 * @returns {Promise<Object>} the updated status payload.
 */
export function dismissUpdate(version) {
  return request('/update/dismiss', { method: 'POST', body: JSON.stringify({ version }) });
}

/**
 * Turns the periodic background update check on or off.
 * @param {boolean} enabled
 * @returns {Promise<Object>} the updated settings payload.
 */
export function setUpdateAutoCheck(enabled) {
  return request(SETTINGS_PATH, { method: 'POST', body: JSON.stringify({ auto_check_enabled: enabled }) });
}

/**
 * Kicks off the in-place update. Progress is polled through getUpdateStatus.
 */
export function startSelfUpdate() {
  return request('/update/selfupdate', { method: 'POST' });
}

/**
 * Records that the user has seen the update disclosure, so it is shown once.
 */
export function markUpdateDisclosed() {
  return request(SETTINGS_PATH, { method: 'POST', body: JSON.stringify({ disclosed: true }) });
}
