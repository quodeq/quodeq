/**
 * Shared repository config management — connect, disconnect,
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
import { MS_PER_SECOND } from '../utils/time.js';

/**
 * Convert a UNIX epoch-seconds timestamp (as sent by the backend) to
 * epoch-milliseconds (as expected by every "N ago" / relativeTime consumer).
 * Null/absent/0 all normalize to null -- there is no meaningful "N ago" for
 * an unset timestamp, and 0 never occurs as a real value here.
 * @param {number|null|undefined} seconds
 * @returns {number|null}
 */
export function epochSecondsToMs(seconds) {
  return typeof seconds === 'number' && seconds ? seconds * MS_PER_SECOND : null;
}

/**
 * One sync job's slot with its finish time in ms (a missing slot becomes an
 * empty one). Every reader of /shared/status goes through this, so the single
 * status cache entry has one shape no matter who fetched it.
 * @param {Object|null|undefined} raw
 * @returns {Object}
 */
export function normalizeSlot(raw) {
  const s = raw || {};
  return { ...s, finishedAt: epochSecondsToMs(s.finishedAt) };
}

// ── Config Management ───────────────────────────────────────────────────────

/**
 * Get the shared repository connection status.
 * @returns {Promise<import('./syncStatus.js').SyncStatus & {publish: Object}>}
 *   lastSynced and each slot's finishedAt are epoch-milliseconds (converted from the backend's epoch
 *   seconds; see epochSecondsToMs). `publish.finishedAt`, if present, is
 *   passed through unconverted (raw epoch seconds) -- no UI consumer currently
 *   formats it as a date.
 */
export async function getSharedStatus() {
  const data = await request('/shared/status');
  return {
    ...data,
    lastSynced: epochSecondsToMs(data?.lastSynced),
    connect: normalizeSlot(data?.connect), refresh: normalizeSlot(data?.refresh), pull: normalizeSlot(data?.pull),
  };
}

/**
 * Connect to a shared repository.
 *
 * The server clones in a background job: PUT answers 202 {started, url} and
 * progress appears under `connect` in /shared/status (see api/syncStatus.js).
 * @param {string} url - Git repository URL
 * @returns {Promise<{started: boolean, url: string}>}
 */
export function connectShared(url) {
  return request('/shared/config', { method: 'PUT', body: JSON.stringify({ url }) });
}

/**
 * How long a disconnect may take. The server stops the shared warm-up and
 * waits for the project in flight before it removes the clone, which on a
 * large project outlasts the default 30 s; the UI must not report a failure
 * for a disconnect that then succeeds.
 */
export const SHARED_DISCONNECT_TIMEOUT_MS = 120000;

/**
 * Disconnect from the shared repository. The server deletes the local clone
 * and requires ?confirm=true; callers show their own confirm step first.
 * @returns {Promise<{configured: boolean}>}
 */
export function disconnectShared() {
  return request('/shared/config?confirm=true', {
    method: 'DELETE',
    timeout: SHARED_DISCONNECT_TIMEOUT_MS,
  });
}
