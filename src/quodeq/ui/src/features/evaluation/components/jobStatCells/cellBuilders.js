/**
 * Cell builders for the live evaluation stat strip (`JobStatStrip`).
 * No React, no network, no DOM — drop-in testable.
 */

import { formatDuration } from '../../../../utils/formatters.js';
import { formatDurationCoarse } from '../../../../utils/dateFormatting.js';
import { isTimeLimitExit } from '../../../../models/exitReason.js';
import { t } from '../../../../strings/index.js';
import { suppressedSuffix, carriedSuffix, formatSevHint } from './derivations.js';
import { SCAN_MODE } from '../scanModes.js';
import { JOB_STATUS } from '../../../../vocab/jobStatus.js';

// This module's own cell-tone values (JobStatStrip's tile accent color).
const CELL_TONE = Object.freeze({
  DEFAULT: 'default', WARNING: 'warning', SUCCESS: 'success', CRITICAL: 'critical', ACCENT: 'accent',
});

// Shared "still counting files" hint, shown while progress is unknown.
const HINT_PREPARING = 'preparing…';

const STATUS_TONE = {
  [JOB_STATUS.RUNNING]: CELL_TONE.WARNING,
  [JOB_STATUS.DONE]: CELL_TONE.SUCCESS,
  [JOB_STATUS.FAILED]: CELL_TONE.CRITICAL,
  [JOB_STATUS.LOST]: CELL_TONE.CRITICAL,
  [JOB_STATUS.CANCELLED]: CELL_TONE.DEFAULT,
};

function statusTone(s) { return STATUS_TONE[s] || CELL_TONE.DEFAULT; }

function progressCell({ overallPct, takenFiles, totalFiles }) {
  const knownAny = totalFiles > 0;
  return {
    label: 'PROGRESS',
    value: knownAny ? `${overallPct}%` : '—',
    hint: knownAny ? `${takenFiles} / ${totalFiles} files` : HINT_PREPARING,
    tone: CELL_TONE.DEFAULT,
  };
}

// A run stopped at its time limit ends a few seconds past it while it
// winds down; only time well past the budget is an overrun.
const OVERRUN_GRACE_S = 60;

// A run past its time budget (budgetS > 0) is flagged in the warning tone.
function elapsedCell(elapsedS, label = 'ELAPSED', hint = null, budgetS = 0) {
  return {
    label,
    value: formatDuration(elapsedS),
    hint,
    tone: budgetS > 0 && elapsedS > budgetS + OVERRUN_GRACE_S ? CELL_TONE.WARNING : CELL_TONE.DEFAULT,
  };
}

function foundCell(liveCount, label = 'FOUND', hint = t('evaluate.liveViolations'), suppressedCount = 0, carriedCount = 0) {
  return {
    label,
    value: liveCount,
    hint: `${hint}${suppressedSuffix(suppressedCount)}${carriedSuffix(carriedCount)}`,
    tone: liveCount > 0 ? CELL_TONE.CRITICAL : CELL_TONE.DEFAULT,
  };
}

function statusHint(s) {
  if (s === JOB_STATUS.RUNNING) return t('evaluate.scanInProgress');
  if (s === JOB_STATUS.DONE) return null;
  if (s === JOB_STATUS.FAILED) return 'see logs';
  if (s === JOB_STATUS.LOST)   return t('evaluate.trackingLost');
  if (s === JOB_STATUS.CANCELLED) return t('evaluate.userCancelled');
  return null;
}

// A finished run's tiles say what the running tiles said, settled: the
// header already says it is complete, so no status tile.
function buildDoneCells(inputs) {
  const dimsKnown = inputs.dimsTotal > 0;
  const filesKnown = inputs.totalFiles > 0;
  return [
    {
      label: t('evaluate.dimensionsTile'),
      value: dimsKnown ? inputs.dimsDone : '—',
      trailing: dimsKnown ? `/ ${inputs.dimsTotal}` : null,
      hint: isTimeLimitExit(inputs.exitReason) ? t('evaluate.timeLimitReached')
        : dimsKnown && inputs.dimsDone === inputs.dimsTotal ? t('evaluate.allDone') : null,
      tone: CELL_TONE.DEFAULT,
    },
    {
      label: t('evaluate.filesThisRun'),
      value: filesKnown ? inputs.takenFiles : '—',
      trailing: filesKnown ? `/ ${inputs.totalFiles}` : null,
      hint: filesHintFor(inputs.scanMode),
      tone: CELL_TONE.DEFAULT,
    },
    foundCell(inputs.liveCount, t('evaluate.newViolationsLabel'), formatSevHint(inputs.sevCounts, t('evaluate.noneFound'))),
    elapsedCell(inputs.elapsedS, t('evaluate.durationLabel'),
      inputs.budgetS > 0 ? t('evaluate.ofBudget', { budget: formatDurationCoarse(inputs.budgetS) }) : t('evaluate.totalHint'),
      inputs.budgetS),
  ];
}

// A clean scan re-reads every file, an incremental one targets what
// changed; no hint until the mode is known.
function filesHintFor(scanMode) {
  if (scanMode === SCAN_MODE.CLEAN) return t('evaluate.filesHint');
  if (scanMode === SCAN_MODE.INCREMENTAL || scanMode === SCAN_MODE.DIFF) return t('evaluate.changedFilesHint');
  return null;
}

function buildRunningCells(inputs) {
  // Running state lives in the card header's pill, so all four tiles carry
  // progress data instead of repeating "running".
  const dc = inputs.dimCycle ?? null;
  const runKnown = inputs.totalFiles > 0;
  const filesHint = filesHintFor(inputs.scanMode);
  // The run's own budget when it has one; an unlimited run keeps the ETA.
  const elapsedHint = inputs.budgetS > 0
    ? t('evaluate.ofBudget', { budget: formatDurationCoarse(inputs.budgetS) })
    : (inputs.etaHint ?? null);
  return [
    {
      // The counter lives in the hint, not the label. Tile labels are a
      // single ellipsized line, and "analyzing · dimension 3 / 4" doesn't fit
      // a quarter-width card — it truncated to "analyzing · dimen…", hiding
      // the only part that carries information. The hint wraps, so it can.
      label: 'analyzing',
      value: dc?.current ?? '—',
      hint: dc
        ? `dim ${dc.index}/${dc.count}${dc.next ? ` · next: ${dc.next}` : ''}`
        : HINT_PREPARING,
      tone: CELL_TONE.ACCENT,
    },
    {
      label: t('evaluate.filesThisRun'),
      value: runKnown ? inputs.takenFiles : '—',
      trailing: runKnown ? `/ ${inputs.totalFiles}` : null,
      hint: runKnown ? filesHint : HINT_PREPARING,
      tone: CELL_TONE.DEFAULT,
    },
    // This run's new findings only: suppressed and carried-forward ones are
    // not what the run found, and the feed below says the rest.
    foundCell(inputs.liveCount, t('evaluate.newViolationsLabel'), formatSevHint(inputs.sevCounts)),
    elapsedCell(inputs.elapsedS, 'elapsed', elapsedHint, inputs.budgetS),
  ];
}

/**
 * @param {string} status — job.status, one of JOB_STATUS's values (vocab/jobStatus.js)
 * @param {object} inputs
 * @param {number} inputs.overallPct
 * @param {number} inputs.takenFiles
 * @param {number} inputs.totalFiles
 * @param {number|null|undefined} inputs.elapsedS
 * @param {number} inputs.liveCount
 * @param {number} [inputs.suppressedCount] — re-found findings already dismissed/deleted
 * @param {number} [inputs.carriedCount] — carried-forward findings the live-feed preference hid
 * @param {string|null} [inputs.exitReason] — job.exitReason; time-limit reasons soften the status cell
 * @param {object|null} [inputs.dimCycle] — from buildDimensionCycle (running only)
 * @param {object} [inputs.sevCounts] — from sumSeverities (running only)
 * @param {string|null} [inputs.scanMode] — from deriveScanMode (running only)
 * @param {number} [inputs.dimsDone] — dimensions finished (done only)
 * @param {number} [inputs.dimsTotal] — dimensions in the run (done only)
 * @param {number} [inputs.budgetS] — the run's time budget in seconds; 0 or absent = unlimited; time past it is flagged
 * @returns {Array<{label,value,hint,tone,trailing?}>} exactly 4 cells.
 */
export function buildJobStatCells(status, inputs) {
  // A run that ended at its time budget is not user-cancelled and not an
  // error: agree with the header pill ("time limit reached") instead of
  // showing "user cancelled" / critical "see logs" under it.
  const timeLimit = isTimeLimitExit(inputs.exitReason);
  const tone = timeLimit ? CELL_TONE.DEFAULT : statusTone(status);
  const statusCell = {
    label: 'STATUS',
    value: status,
    tone,
    hint: timeLimit ? t('evaluate.timeLimitReached') : statusHint(status),
  };

  if (status === JOB_STATUS.DONE) {
    return buildDoneCells(inputs);
  }

  if (status === JOB_STATUS.RUNNING) {
    return buildRunningCells(inputs);
  }

  // failed / lost / cancelled — same shape as before, status-tone differs
  return [
    statusCell,
    progressCell(inputs),
    foundCell(inputs.liveCount, 'FOUND', t('evaluate.liveViolations'), inputs.suppressedCount, inputs.carriedCount),
    elapsedCell(inputs.elapsedS, 'ELAPSED', inputs.etaHint ?? null),
  ];
}
