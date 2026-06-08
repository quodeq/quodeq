/**
 * Pure helpers for the live evaluation stat strip (`JobStatStrip`).
 * No React, no network, no DOM — drop-in testable.
 */

// Throughput estimate tuning. The eval completes only a few files per MINUTE
// (one slow LLM call per file), so the rate is shown per minute and measured
// over a wide window: at ~3-10 files/min a short window sees too few files to
// be stable and would flicker to "estimating…". The window also reflects
// *current* speed (cache-hit bursts vs slow misses, per-dimension shifts)
// rather than a startup-biased lifetime average.
export const RATE_WINDOW_MS = 120000;  // 2-min sliding window the buffer is trimmed to
const RATE_MIN_SPAN_MS = 30000;        // refuse to estimate from < this much data

/**
 * Files/sec from a buffer of {t, taken} samples (t = epoch ms, ascending).
 * Returns null — meaning "no honest estimate yet" — when there are fewer than
 * two samples, the window spans less than RATE_MIN_SPAN_MS, or files have not
 * advanced across the window (a stall).
 * @param {Array<{t:number, taken:number}>} samples
 * @returns {number|null}
 */
export function computeRate(samples) {
  if (!Array.isArray(samples) || samples.length < 2) return null;
  const oldest = samples[0];
  const newest = samples[samples.length - 1];
  const spanMs = newest.t - oldest.t;
  if (spanMs < RATE_MIN_SPAN_MS) return null;
  const dFiles = newest.taken - oldest.taken;
  if (dFiles <= 0) return null;
  return dFiles / (spanMs / 1000);
}

/**
 * "~5 files/min" from a files/SECOND rate. The eval runs only a few files per
 * minute, so per-second would read ~0.08; per-minute is legible. Integer
 * at/above 1/min, one decimal below. null when unusable.
 */
export function formatRate(rate) {
  if (rate == null || !Number.isFinite(rate) || rate <= 0) return null;
  const perMin = rate * 60;
  const shown = perMin >= 1 ? String(Math.round(perMin)) : perMin.toFixed(1);
  return `~${shown} files/min`;
}

/**
 * Coarse, human-readable time remaining from files-left + files/sec rate.
 * "finishing" near the end; "~N min left"; "~Hh left" / "~Hh Mm left".
 * Returns "estimating…" if rate is unusable (caller normally gates first).
 */
export function formatEta(remainingFiles, rate) {
  if (!(rate > 0) || !Number.isFinite(rate)) return 'estimating…';
  if (remainingFiles <= 0) return 'finishing';
  const etaSec = remainingFiles / rate;
  if (etaSec <= 45) return 'finishing';
  if (etaSec < 3600) {
    const rawMin = etaSec / 60;
    let min = rawMin < 10 ? Math.max(1, Math.round(rawMin)) : Math.round(rawMin / 5) * 5;
    if (min >= 60) return '~1h left';
    return `~${min} min left`;
  }
  let hours = Math.floor(etaSec / 3600);
  let min = Math.round(((etaSec % 3600) / 60) / 5) * 5;
  if (min === 60) { hours += 1; min = 0; }
  return min === 0 ? `~${hours}h left` : `~${hours}h ${min}m left`;
}

/**
 * ELAPSED subtext for a running job: "~5 files/min · ~5h left".
 *  - null  when totalFiles is unknown (the PROGRESS card shows "preparing…").
 *  - "estimating…" when total is known but the rate isn't trustworthy yet.
 * @param {{rate:number|null, takenFiles:number, totalFiles:number}} args
 */
export function buildEtaHint({ rate, takenFiles, totalFiles }) {
  if (!(totalFiles > 0)) return null;
  const rateStr = formatRate(rate);
  if (rateStr == null) return 'estimating…';
  return `${rateStr} · ${formatEta(totalFiles - takenFiles, rate)}`;
}

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
    elapsedCell(inputs.elapsedS, 'ELAPSED', inputs.etaHint ?? null),
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
