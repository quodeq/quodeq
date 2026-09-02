/**
 * Shared repository config management — connect, disconnect, refresh,
 * and connection status.
 *
 * Timestamp units: the backend (services/shared_repo.py's published_meta and
 * last_synced_at) sends publishedAt/lastSynced as UNIX epoch SECONDS (git log
 * `%ct` is an int; st_mtime is a float) -- but every "N ago" consumer
 * (relativeTime in components/LastFetchedLine.jsx) expects milliseconds, same
 * as Date.now()/`new Date(ms)`. Converting seconds->ms is done once, here, at
 * the API-client boundary, so every consumer downstream always sees ms and
 * never has to know the wire units. Passing raw seconds through would render
 * as a 1970 date ("57 years ago") -- see epochSecondsToMs below.
 */

import { request } from './request.js';

/**
 * Convert a UNIX epoch-seconds timestamp (as sent by the backend) to
 * epoch-milliseconds (as expected by every "N ago" / relativeTime consumer).
 * Null/absent/0 all normalize to null -- there is no meaningful "N ago" for
 * an unset timestamp, and 0 never occurs as a real value here.
 * @param {number|null|undefined} seconds
 * @returns {number|null}
 */
export function epochSecondsToMs(seconds) {
  return typeof seconds === 'number' && seconds ? seconds * 1000 : null;
}

// ── Config Management ───────────────────────────────────────────────────────

/**
 * Get the shared repository connection status.
 * @returns {Promise<{configured: boolean, url: string|null, lastSynced: number|null, publish: Object}>}
 *   lastSynced is epoch-milliseconds (converted from the backend's epoch
 *   seconds; see epochSecondsToMs). `publish.finishedAt`, if present, is
 *   passed through unconverted (raw epoch seconds) -- no UI consumer currently
 *   formats it as a date.
 */
export async function getSharedStatus() {
  const data = await request('/shared/status');
  return {
    ...data,
    lastSynced: epochSecondsToMs(data?.lastSynced),
  };
}

/**
 * Connect to a shared repository.
 * @param {string} url - Git repository URL
 * @returns {Promise<{configured: boolean, url: string}>}
 */
export function connectShared(url) {
  return request('/shared/config', {
    method: 'PUT',
    body: JSON.stringify({ url }),
  });
}

/**
 * Disconnect from the shared repository.
 * @returns {Promise<{configured: boolean}>}
 */
export function disconnectShared() {
  return request('/shared/config', {
    method: 'DELETE',
  });
}

/**
 * Refresh the shared repository (fetch latest changes).
 * @returns {Promise<{stale: boolean, lastSynced: string}>}
 */
export function refreshShared() {
  return request('/shared/refresh', {
    method: 'POST',
  });
}
