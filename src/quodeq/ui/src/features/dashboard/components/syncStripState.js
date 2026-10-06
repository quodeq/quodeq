import { isSlotActive } from '../../../api/syncStatus.js';
import { SYNC_KIND, SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { t } from '../../../strings/index.js';
import { formatSize } from '../../../utils/formatSize.js';

// The one row the sync strip shows (spec 4.2), in the order they outrank each other.
export const STRIP_STATE = Object.freeze({
  HIDDEN: 'hidden',
  PROGRESS: 'progress', // a connect or refresh job is working
  WARMING: 'warming', // the server is still warming cards it has not listed yet
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
 *
 * Warming (the server lists a card only once it is fully readable and
 * counts the rest) comes right after a running job: the team's results are
 * still arriving, and the strip says how many are ready so nobody wonders
 * whether the missing cards are on their way.
 * @param {{status: Object|undefined, offline?: boolean, updateFailed?: boolean, loadFailed?: boolean,
 *   warming?: {active: boolean, done: number, total: number, remaining: number}|null}} input
 * @returns {{kind: string, slot?: Object, slotKind?: string, warming?: Object}}
 */
export function pickStripState({ status, offline = false, updateFailed = false, loadFailed = false, warming = null }) {
  const connect = status?.connect;
  if (isSlotActive(connect)) return { kind: STRIP_STATE.PROGRESS, slot: connect, slotKind: SYNC_KIND.CONNECT };
  if (!status?.configured) return { kind: STRIP_STATE.HIDDEN };
  return configuredRow({ status, offline, updateFailed, loadFailed, warming });
}

// The rows a configured repository can show, in rank order (see pickStripState).
function configuredRow({ status, offline, updateFailed, loadFailed, warming }) {
  const { connect, refresh } = status;
  if (isSlotActive(refresh)) return { kind: STRIP_STATE.PROGRESS, slot: refresh, slotKind: SYNC_KIND.REFRESH };
  if (warming?.active) return { kind: STRIP_STATE.WARMING, warming };
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
    case SYNC_PHASE.RESOLVING:
      return t('sync.resolving', { percent: Math.round(slot.percent ?? 0) });
    case SYNC_PHASE.CHECKOUT:
      return t('sync.checkingOut', { percent: Math.round(slot.percent ?? 0) });
    default:
      return t('sync.reading', { count: slot.projectsFound ?? 0 });
  }
}

/**
 * The warming row's copy: how many of the team's cards are ready so far.
 * @param {{done: number, total: number}} warming
 * @returns {string}
 */
export function warmingLabel(warming) {
  return t('sync.warming', { done: warming.done ?? 0, total: warming.total ?? 0 });
}

/**
 * Whether the running job reports a percent the bar can show; the download
 * and git's resolving and checkout do, connecting and reading do not.
 * @param {Object} slot
 * @returns {number|null}
 */
export function barPercent(slot) {
  const withPercent = slot.phase === SYNC_PHASE.DOWNLOADING || slot.phase === SYNC_PHASE.RESOLVING || slot.phase === SYNC_PHASE.CHECKOUT;
  return withPercent && typeof slot.percent === 'number' ? slot.percent : null;
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
    case SYNC_PHASE.RESOLVING:
    case SYNC_PHASE.CHECKOUT:
      return t('sync.resolvingAnnounce');
    default:
      return t('sync.readingAnnounce');
  }
}
