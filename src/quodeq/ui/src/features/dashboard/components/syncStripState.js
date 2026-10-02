import { isSlotActive } from '../../../api/syncStatus.js';
import { SYNC_KIND, SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { connectSlotError } from '../../../hooks/connectSlotError.js';
import { t } from '../../../strings/index.js';
import { formatSize } from '../../../utils/formatSize.js';

// The one row the sync strip shows (spec 4.2), in the order they outrank each other.
export const STRIP_STATE = Object.freeze({
  HIDDEN: 'hidden',
  PROGRESS: 'progress', // a connect or refresh job is working
  OFFLINE: 'offline', // the status poll fails; showing the last-known results
  UPDATE_FAILED: 'updateFailed',
  LOAD_FAILED: 'loadFailed', // the team list never loaded and no refresh failure explains it
  CONNECT_FAILED: 'connectFailed',
  SYNCED: 'synced',
});

/**
 * A repository URL as host/path: "https://github.com/team/results.git" and
 * "git@github.com:team/results.git" both read "github.com/team/results".
 * @param {string|null|undefined} url
 * @returns {string}
 */
export function repoLabel(url) {
  if (!url) return '';
  return url
    .replace(/^[a-z][a-z0-9+.-]*:\/\//i, '') // scheme
    .replace(/^[^@/]+@/, '') // user@
    .replace(/^([^/:]+):(?!\d)/, '$1/') // scp-style host:path
    .replace(/\/+$/, '')
    .replace(/\.git$/, '');
}

// A finished ERROR only counts while no later job of the other kind has finished since.
function isCurrentError(slot, other) {
  if (slot?.phase !== SYNC_PHASE.ERROR) return false;
  return !(other?.finishedAt && slot.finishedAt && other.finishedAt > slot.finishedAt);
}

/**
 * Which row the strip shows. A running connect is shown even before a
 * repository is configured (a first connect only configures one when it
 * succeeds); otherwise nothing renders until one is.
 * @param {{status: Object|undefined, offline?: boolean, updateFailed?: boolean, loadFailed?: boolean}} input
 * @returns {{kind: string, slot?: Object, slotKind?: string}}
 */
export function pickStripState({ status, offline = false, updateFailed = false, loadFailed = false }) {
  const connect = status?.connect;
  const refresh = status?.refresh;
  if (isSlotActive(connect)) return { kind: STRIP_STATE.PROGRESS, slot: connect, slotKind: SYNC_KIND.CONNECT };
  if (!status?.configured) return { kind: STRIP_STATE.HIDDEN };
  if (isSlotActive(refresh)) return { kind: STRIP_STATE.PROGRESS, slot: refresh, slotKind: SYNC_KIND.REFRESH };
  if (offline) return { kind: STRIP_STATE.OFFLINE };
  if (updateFailed || isCurrentError(refresh, connect)) return { kind: STRIP_STATE.UPDATE_FAILED };
  if (loadFailed) return { kind: STRIP_STATE.LOAD_FAILED };
  if (isCurrentError(connect, refresh)) return { kind: STRIP_STATE.CONNECT_FAILED, slot: connect };
  return { kind: STRIP_STATE.SYNCED };
}

/**
 * The progress row's copy for a running job.
 * @param {Object} slot - the running connect or refresh slot
 * @param {string} slotKind - SYNC_KIND.CONNECT or SYNC_KIND.REFRESH
 * @param {string|null} url - the repository being synced
 * @returns {string}
 */
export function progressLabel(slot, slotKind, url) {
  switch (slot.phase) {
    case SYNC_PHASE.CONNECTING:
      return slotKind === SYNC_KIND.CONNECT ? t('sync.connecting', { host: repoLabel(url) }) : t('sync.updating');
    case SYNC_PHASE.DOWNLOADING: {
      const size = formatSize(slot.bytes);
      return typeof slot.percent === 'number' && size
        ? t('sync.downloading', { percent: Math.round(slot.percent), size })
        : t('sync.downloadingNoSize');
    }
    default:
      return t('sync.reading', { count: slot.projectsFound ?? 0 });
  }
}

/** The failed connect's display copy, mapped from its code like every other API error. */
export function connectFailureLabel(slot) {
  return t('sync.failedWithRetry', { message: connectSlotError(slot, 'projects.connectFailed') });
}
