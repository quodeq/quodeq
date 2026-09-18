/**
 * Update notifications API — app version check, dismiss, and auto-check
 * settings.
 */

import { request } from './request.js';

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
 */
export function dismissUpdate(version) {
  return request('/update/dismiss', { method: 'POST', body: JSON.stringify({ version }) });
}

/**
 * Turns the periodic background update check on or off.
 */
export function setUpdateAutoCheck(enabled) {
  return request('/update/settings', { method: 'POST', body: JSON.stringify({ auto_check_enabled: enabled }) });
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
  return request('/update/settings', { method: 'POST', body: JSON.stringify({ disclosed: true }) });
}
