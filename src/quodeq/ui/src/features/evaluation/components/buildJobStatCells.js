/**
 * Pure helpers for the live evaluation stat strip (`JobStatStrip`).
 * No React, no network, no DOM — drop-in testable.
 */

export function formatClock(s) {
  if (s == null || !Number.isFinite(s)) return '—';
  const total = Math.max(0, Math.floor(s));
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

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
    value: formatClock(elapsedS),
    hint,
    tone: 'default',
  };
}

function foundCell(liveCount, label = 'FOUND', hint = 'live violations') {
  return {
    label,
    value: liveCount,
    hint,
    tone: liveCount > 0 ? 'critical' : 'default',
  };
}

/**
 * @param {string} status — job.status: running | done | completed | failed | lost | cancelled
 * @param {object} inputs
 * @param {number} inputs.overallPct
 * @param {number} inputs.takenFiles
 * @param {number} inputs.totalFiles
 * @param {number|null|undefined} inputs.elapsedS
 * @param {number} inputs.liveCount
 * @returns {Array<{label,value,hint,tone}>} exactly 4 cells.
 */
export function buildJobStatCells(status, inputs) {
  const tone = statusTone(status);
  const statusCell = { label: 'STATUS', value: status, tone, hint: statusHint(status) };

  if (status === 'done' || status === 'completed') {
    return [
      statusCell,
      { label: 'SCANNED', value: inputs.totalFiles > 0 ? inputs.totalFiles : '—', hint: 'files', tone: 'default' },
      foundCell(inputs.liveCount, 'VIOLATIONS', severityHint(inputs.liveCount)),
      elapsedCell(inputs.elapsedS, 'DURATION', 'total'),
    ];
  }
  // running / failed / lost / cancelled — same shape, status-tone differs
  return [
    statusCell,
    progressCell(inputs),
    foundCell(inputs.liveCount),
    elapsedCell(inputs.elapsedS),
  ];
}

function statusHint(s) {
  if (s === 'running') return 'scan in progress';
  if (s === 'done' || s === 'completed') return null;
  if (s === 'failed') return 'see logs';
  if (s === 'lost')   return 'tracking lost';
  if (s === 'cancelled') return 'user cancelled';
  return null;
}

function severityHint(n) {
  if (!n) return 'none';
  return `${n} total`;
}
