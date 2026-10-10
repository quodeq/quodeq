import { RESCORE_STATE } from '../../vocab/rescoreState.js';
import { t } from '../../strings/index.js';

/** What the rebuild strip is showing. */
export const REBUILD_STATE = Object.freeze({
  IDLE: 'idle', // nothing running: the strip is not rendered
  LISTING: 'listing', // a formula pass was requested and is still listing its runs
  RESCORING: 'rescoring', // the formula pass is rewriting runs
  WARMING: 'warming', // the warm-up queue is rebuilding project summaries
  DONE: 'done', // a pass or the queue just finished; shown for a beat, then idle
  FAILED: 'failed', // the last formula pass raised; stays until retried
});

const PERCENT_MAX = 100;
const BUSY = new Set([REBUILD_STATE.LISTING, REBUILD_STATE.RESCORING, REBUILD_STATE.WARMING]);

/** True for the states that mean work is in progress. */
export function isBusyState(kind) {
  return BUSY.has(kind);
}

/**
 * The strip state from the two things that rebuild scores: the grade-formula
 * pass the app-level tracker follows (`rescore` is its last payload, `tracking`
 * whether it is still following one), and the warm-up queue's snapshot from
 * the last project list. A running pass wins over the warm-up: the pass
 * invalidates every project when it lands, so the warm-up follows it anyway.
 * @param {{rescore?: Object, tracking: boolean, warmup?: Object|null}} input
 * @returns {{kind: string, done: number, total: number, name?: string|null}}
 */
export function pickRebuildState({ rescore, tracking, warmup }) {
  if (tracking) {
    const total = rescore?.total ?? 0;
    if (total === 0) return { kind: REBUILD_STATE.LISTING, done: 0, total: 0 };
    return { kind: REBUILD_STATE.RESCORING, done: rescore?.done ?? 0, total };
  }
  if (rescore?.state === RESCORE_STATE.ERROR) return { kind: REBUILD_STATE.FAILED, done: 0, total: 0 };
  if (warmup?.active) {
    return {
      kind: REBUILD_STATE.WARMING,
      done: warmup.projectsDone ?? 0,
      total: warmup.projectsTotal ?? 0,
      name: warmup.currentProjectName ?? null,
    };
  }
  return { kind: REBUILD_STATE.IDLE, done: 0, total: 0 };
}

/**
 * The bar's percent for a state, or null when the state has no measure
 * (listing runs has nothing to count yet).
 * @param {{kind: string, done: number, total: number}} state
 * @returns {number|null}
 */
export function rebuildPercent(state) {
  if (state.kind !== REBUILD_STATE.RESCORING && state.kind !== REBUILD_STATE.WARMING) return null;
  if (!state.total) return null;
  return Math.min(PERCENT_MAX, Math.round((state.done / state.total) * PERCENT_MAX));
}

/**
 * The row's copy: the short label, the muted detail beside it, and the
 * phase-only text the live region announces (the counts change on every
 * poll and would be re-read each time). `finished` is the busy state the
 * done row follows, so it can say what finished.
 * @param {{kind: string, done: number, total: number, name?: string|null}} state
 * @param {{kind: string, total: number}|null} [finished]
 * @returns {{label: string, meta: string, announce: string}}
 */
export function rebuildCopy(state, finished = null) {
  switch (state.kind) {
    case REBUILD_STATE.LISTING:
      return { label: t('rebuild.rescoring'), meta: t('rebuild.listingRuns'), announce: t('rebuild.rescoringAnnounce') };
    case REBUILD_STATE.RESCORING:
      return {
        label: t('rebuild.rescoring'),
        meta: t('rebuild.rescoringRuns', { done: state.done, total: state.total }),
        announce: t('rebuild.rescoringAnnounce'),
      };
    case REBUILD_STATE.WARMING:
      return {
        label: t('rebuild.warming'),
        meta: state.name
          ? t('rebuild.warmingCurrent', { done: state.done, total: state.total, name: state.name })
          : t('rebuild.warmingProjects', { done: state.done, total: state.total }),
        announce: t('rebuild.warmingAnnounce'),
      };
    case REBUILD_STATE.DONE:
      return { label: t('rebuild.done'), meta: doneMeta(finished), announce: t('rebuild.done') };
    case REBUILD_STATE.FAILED:
      return { label: t('rebuild.failed'), meta: t('rebuild.failedMeta'), announce: t('rebuild.failedMeta') };
    default:
      return { label: '', meta: '', announce: '' };
  }
}

function doneMeta(finished) {
  if (!finished || !finished.total) return '';
  if (finished.kind === REBUILD_STATE.WARMING) return t('rebuild.doneProjects', { total: finished.total });
  return t('rebuild.doneRuns', { total: finished.total });
}
