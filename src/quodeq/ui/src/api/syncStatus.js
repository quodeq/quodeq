import { request } from './request.js';
import { epochSecondsToMs } from './sharedStatus.js';
import { SYNC_ACTIVE_PHASES } from '../vocab/syncPhase.js';

/**
 * One background sync job as GET /shared/status reports it.
 * @typedef {Object} SlotView
 * @property {string} state - idle | running | done | error
 * @property {string|null} kind - connect | refresh | pull
 * @property {string|null} phase - connecting | downloading | reading | done | error
 * @property {number|null} percent
 * @property {number|null} bytes
 * @property {number|null} projectsFound
 * @property {string|null} error
 * @property {string|null} code
 * @property {number|null} finishedAt - epoch ms (converted from the wire seconds)
 * @property {string|null} [project] - pull slot only
 * @property {string|null} [projectId] - pull slot only
 * @property {string|null} [projectName] - pull slot only
 * @property {boolean|null} [renamed] - pull slot only
 * @property {string|null} [conflictKind] - pull slot, on a collision; passed through
 * @property {string|null} [sourceProjectId] - pull slot, on a collision; passed through
 */

/**
 * @typedef {Object} SyncStatus
 * @property {boolean} configured
 * @property {string|null} url
 * @property {number|null} lastSynced - epoch ms
 * @property {string} repoState
 * @property {boolean} syncing
 * @property {SlotView} connect
 * @property {SlotView} refresh
 * @property {SlotView} pull
 */

function slot(raw) {
  const s = raw || {};
  return { ...s, finishedAt: epochSecondsToMs(s.finishedAt) };
}

/** The shared repository's connection and its three sync jobs, timestamps in ms. */
export async function getSyncStatus() {
  const d = await request('/shared/status');
  return {
    ...d,
    lastSynced: epochSecondsToMs(d?.lastSynced),
    connect: slot(d?.connect), refresh: slot(d?.refresh), pull: slot(d?.pull),
  };
}

/** Start a background refresh. Answers 202 {started}. */
export function startRefresh() { return request('/shared/refresh', { method: 'POST' }); }

/** Start a background pull of a shared project. Answers 202 {started, project}. */
export function startPull(projectId, action) {
  return request(`/shared/projects/${encodeURIComponent(projectId)}/pull`, {
    method: 'POST', body: JSON.stringify(action ? { action } : {}),
  });
}

/** The invite text for teammates. */
export function getInvite() { return request('/shared/invite'); }

/** True while the slot's job is connecting, downloading or reading. */
export function isSlotActive(s) { return Boolean(s?.phase) && SYNC_ACTIVE_PHASES.has(s.phase); }
/** True when any of the connect, refresh or pull slots is active. */
export function anyActive(status) { return [status?.connect, status?.refresh, status?.pull].some(isSlotActive); }
