/**
 * Cell builders for the live evaluation stat strip (`JobStatStrip`).
 * No React, no network, no DOM — drop-in testable.
 */

import { formatDuration } from '../../../../utils/formatters.js';
import { isTimeLimitExit } from '../../../../models/exitReason.js';
import { t } from '../../../../strings/index.js';
import { suppressedSuffix, carriedSuffix, formatSevHint } from './derivations.js';

const STATUS_TONE = {
  running: 'warning',
  done: 'success',
  completed: 'success',
  failed: 'critical',
  lost: 'critical',
  cancelled: 'default',
};

function statusTone(s) { return STATUS_TONE[s] || 'default'; }

function progressCell({ overallPct, takenFiles, totalFiles }) {
  const knownAny = totalFiles > 0;
  return {
    label: 'PROGRESS',
    value: knownAny ? `${overallPct}%` : '—',
    hint: knownAny ? `${takenFiles} / ${totalFiles} files` : 'preparing…',
    tone: 'default',
  };
}

function elapsedCell(elapsedS, label = 'ELAPSED', hint = null) {
  return {
    label,
    value: formatDuration(elapsedS),
    hint,
    tone: 'default',
  };
}

function foundCell(liveCount, label = 'FOUND', hint = t('evaluate.liveViolations'), suppressedCount = 0, carriedCount = 0) {
  return {
    label,
    value: liveCount,
    hint: `${hint}${suppressedSuffix(suppressedCount)}${carriedSuffix(carriedCount)}`,
    tone: liveCount > 0 ? 'critical' : 'default',
  };
}

function statusHint(s) {
  if (s === 'running') return t('evaluate.scanInProgress');
  if (s === 'done' || s === 'completed') return null;
  if (s === 'failed') return 'see logs';
  if (s === 'lost')   return t('evaluate.trackingLost');
  if (s === 'cancelled') return t('evaluate.userCancelled');
  return null;
}

function severityHint(n) {
  if (!n) return 'none';
  return `${n} total`;
}

function buildDoneCells(statusCell, inputs) {
  return [
    statusCell,
    { label: 'SCANNED', value: inputs.totalFiles > 0 ? inputs.totalFiles : '—', hint: 'files', tone: 'default' },
    foundCell(inputs.liveCount, 'VIOLATIONS', severityHint(inputs.liveCount), inputs.suppressedCount, inputs.carriedCount),
    elapsedCell(inputs.elapsedS, 'DURATION', 'total'),
  ];
}

function buildRunningCells(inputs) {
  // Running state lives in the card header's pill, so all four tiles carry
  // progress data instead of repeating "running".
  const dc = inputs.dimCycle ?? null;
  const runKnown = inputs.totalFiles > 0;
  const modeHint = inputs.scanMode === 'incremental' ? t('evaluate.modeIncremental')
    : inputs.scanMode === 'clean' ? t('evaluate.modeFullRescan') : '';
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
        : 'preparing…',
      tone: 'accent',
    },
    {
      label: t('evaluate.filesThisRun'),
      value: runKnown ? inputs.takenFiles : '—',
      trailing: runKnown ? `/ ${inputs.totalFiles}` : null,
      hint: runKnown ? `${inputs.overallPct}%${modeHint}` : 'preparing…',
      tone: 'default',
    },
    foundCell(inputs.liveCount, 'violations', formatSevHint(inputs.sevCounts), inputs.suppressedCount, inputs.carriedCount),
    elapsedCell(inputs.elapsedS, 'elapsed', inputs.etaHint ?? null),
  ];
}

/**
 * @param {string} status — job.status: running | done | completed | failed | lost | cancelled
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
 * @returns {Array<{label,value,hint,tone,trailing?}>} exactly 4 cells.
 */
export function buildJobStatCells(status, inputs) {
  // A run that ended at its time budget is not user-cancelled and not an
  // error: agree with the header pill ("time limit reached") instead of
  // showing "user cancelled" / critical "see logs" under it.
  const timeLimit = isTimeLimitExit(inputs.exitReason);
  const tone = timeLimit ? 'default' : statusTone(status);
  const statusCell = {
    label: 'STATUS',
    value: status,
    tone,
    hint: timeLimit ? t('evaluate.timeLimitReached') : statusHint(status),
  };

  if (status === 'done' || status === 'completed') {
    return buildDoneCells(statusCell, inputs);
  }

  if (status === 'running') {
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
