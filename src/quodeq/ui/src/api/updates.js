/**
 * Update notifications API — app version check, dismiss, and auto-check
 * settings.
 */

import { request } from './request.js';

export function getUpdateStatus() {
  return request('/update/status');
}

export function checkForUpdates() {
  return request('/update/check', { method: 'POST' });
}

export function dismissUpdate(version) {
  return request('/update/dismiss', { method: 'POST', body: JSON.stringify({ version }) });
}

export function setUpdateAutoCheck(enabled) {
  return request('/update/settings', { method: 'POST', body: JSON.stringify({ auto_check_enabled: enabled }) });
}

export function startSelfUpdate() {
  return request('/update/selfupdate', { method: 'POST' });
}

export function markUpdateDisclosed() {
  return request('/update/settings', { method: 'POST', body: JSON.stringify({ disclosed: true }) });
}
