import { isSlotActive } from '../../../api/syncStatus.js';
import { SYNC_KIND, SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { t } from '../../../strings/index.js';
import { formatSize } from '../../../utils/formatSize.js';

// The one row the sync strip shows (spec 4.2), in the order they outrank each other.
export const STRIP_STATE = Object.freeze({
  HIDDEN: 'hidden',
  PROGRESS: 'progress', // a connect or refresh job is working
  OFFLINE: 'offline', // the status poll fails; showing the last-known results
  UPDATE_FAILED: 'updateFailed',
  LOAD_FAILED: 'loadFailed', // the team list never loaded and no refresh failure explains it
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

// A finished ERROR only counts while no job of the other kind has finished since.
function isCurrentError(slot, other) {
  if (slot?.phase !== SYNC_PHASE.ERROR) return false;
  return !(other?.finishedAt && slot.finishedAt && other.finishedAt > slot.finishedAt);
}

/**
 * Which row the strip shows, in this order: a running connect, then (only
 * with a repository configured) a running refresh, offline, update failed,
 * load failed, synced.
 *
 * A running connect shows even before a repository is configured (a first
 * connect only configures one when it succeeds). A FAILED connect never
 * shows here: its error belongs to the connect card, which is where the URL
 * was typed and where it is retried. With a repository configured (a failed
 * "change repository") the strip keeps describing the repository that still
 * works, so it falls through to synced with its count and update action;
 * without one the strip is hidden and the page opens the card with the error
 * (TeamResultsArea).
 *
 * A refresh ERROR only counts while no connect has finished after it.
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

/**
 * What the live region announces for a running job: the phase only, so a
 * percent or count that moves on every poll is not read out each time.
 * @param {Object} slot - the running connect or refresh slot
 * @param {string} slotKind - SYNC_KIND.CONNECT or SYNC_KIND.REFRESH
 * @param {string|null} url - the repository being synced
 * @returns {string}
 */
export function progressAnnouncement(slot, slotKind, url) {
  switch (slot.phase) {
    case SYNC_PHASE.CONNECTING:
      return progressLabel(slot, slotKind, url);
    case SYNC_PHASE.DOWNLOADING:
      return t('sync.downloadingNoSize');
    default:
      return t('sync.readingAnnounce');
  }
}
