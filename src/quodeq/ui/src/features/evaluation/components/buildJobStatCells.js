/**
 * Pure helpers for the live evaluation stat strip (`JobStatStrip`).
 * No React, no network, no DOM — drop-in testable.
 */

import { computeOverallProgress } from './scanProgressTotals.js';

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

/**
 * Milliseconds from an elapsed-ms value to the next whole-second boundary.
 * The ELAPSED display shows `floor(elapsedMs / 1000)`, so it flips exactly on
 * these boundaries; scheduling the next re-render for this delay (instead of a
 * fixed 1s interval whose phase is fixed at mount and drifts against the
 * boundary) keeps the clock ticking evenly and never accumulates drift. Always
 * in (0, 1000]; defaults to 1000 for a non-finite input.
 */
export function msUntilNextSecond(elapsedMs) {
  if (!Number.isFinite(elapsedMs)) return 1000;
  const rem = ((elapsedMs % 1000) + 1000) % 1000;  // normalize negatives
  return 1000 - rem;
}

export function formatClock(s) {
  if (s == null || !Number.isFinite(s)) return '—';
  const total = Math.max(0, Math.floor(s));
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

/**
 * Where the run is in its dimension sequence, for the "analyzing" KPI tile.
 * Returns null when the progress payload carries no dimensions. `index` is
 * 1-based; `next` is the first pending dim after the running one (null on the
 * last dimension). The display name prefers `progress.currentDimension` —
 * it flips slightly ahead of the per-dim states during handover.
 * @returns {{current:string|null, index:number, count:number, next:string|null}|null}
 */
export function buildDimensionCycle(progress) {
  const dims = progress?.dimensions || [];
  if (dims.length === 0) return null;
  let runningIdx = dims.findIndex((d) => d?.state === 'running');
  if (runningIdx === -1) {
    const doneCount = dims.filter((d) => d?.state === 'done').length;
    runningIdx = Math.min(doneCount, dims.length - 1);
  }
  const next = dims.slice(runningIdx + 1).find((d) => d?.state === 'pending')?.id ?? null;
  return {
    current: progress?.currentDimension ?? dims[runningIdx]?.id ?? null,
    index: runningIdx + 1,
    count: dims.length,
    next,
  };
}

/** Severity buckets across the live feed's `{dim: Violation[]}` map. */
export function sumSeverities(liveViolations) {
  const counts = { critical: 0, major: 0, minor: 0 };
  for (const vs of Object.values(liveViolations || {})) {
    for (const v of vs || []) {
      const sev = String(v?.severity || '').toLowerCase();
      if (sev in counts) counts[sev] += 1;
    }
  }
  return counts;
}

/** "1 critical · 4 major" — zero buckets omitted; "none yet" when all zero. */
export function formatSevHint(counts) {
  const parts = ['critical', 'major', 'minor']
    .filter((k) => counts?.[k] > 0)
    .map((k) => `${counts[k]} ${k}`);
  return parts.length > 0 ? parts.join(' · ') : 'none yet';
}

/**
 * The run's scan mode, derived from coverage. The job/progress payloads don't
 * echo the cleanScan flag back, but coverage tells the same story: cached
 * results exist only on incremental runs. Null while coverage is unknown
 * (legacy dims, preparing) — callers show a placeholder.
 */
export function deriveScanMode(progress) {
  if (!progress) return null;
  const { cachedFiles, projectTotal } = computeOverallProgress(progress);
  if (cachedFiles == null || !(projectTotal > 0)) return null;
  return cachedFiles > 0 ? 'incremental' : 'clean scan';
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

/**
 * The count of findings this run re-discovered but the user had already
 * dismissed or deleted, as a hint suffix. Without it the counter silently
 * drops a number that can dwarf what's shown — on a project with a triage
 * history the scan re-finds hundreds of suppressed findings every run.
 */
export function suppressedSuffix(suppressedCount) {
  if (!(suppressedCount > 0)) return '';
  return ` · ${suppressedCount} suppressed`;
}

/**
 * The count of findings this run re-discovered that the live-findings-only
 * preference filtered out before FOUND ever saw them, as a hint suffix.
 * Without it the cell silently drops a number the feed already discloses
 * next to the list, so the strip and the feed can look like they disagree.
 */
export function carriedSuffix(carriedCount) {
  if (!(carriedCount > 0)) return '';
  return ` · ${carriedCount} carried forward`;
}

function foundCell(liveCount, label = 'FOUND', hint = 'live violations', suppressedCount = 0, carriedCount = 0) {
  return {
    label,
    value: liveCount,
    hint: `${hint}${suppressedSuffix(suppressedCount)}${carriedSuffix(carriedCount)}`,
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
 * @param {number} [inputs.suppressedCount] — re-found findings already dismissed/deleted
 * @param {number} [inputs.carriedCount] — carried-forward findings the live-feed preference hid
 * @param {object|null} [inputs.dimCycle] — from buildDimensionCycle (running only)
 * @param {object} [inputs.sevCounts] — from sumSeverities (running only)
 * @param {string|null} [inputs.scanMode] — from deriveScanMode (running only)
 * @returns {Array<{label,value,hint,tone,trailing?}>} exactly 4 cells.
 */
export function buildJobStatCells(status, inputs) {
  const tone = statusTone(status);
  const statusCell = { label: 'STATUS', value: status, tone, hint: statusHint(status) };

  if (status === 'done' || status === 'completed') {
    return [
      statusCell,
      { label: 'SCANNED', value: inputs.totalFiles > 0 ? inputs.totalFiles : '—', hint: 'files', tone: 'default' },
      foundCell(inputs.liveCount, 'VIOLATIONS', severityHint(inputs.liveCount), inputs.suppressedCount, inputs.carriedCount),
      elapsedCell(inputs.elapsedS, 'DURATION', 'total'),
    ];
  }

  if (status === 'running') {
    // Running state lives in the card header's pill, so all four tiles carry
    // progress data instead of repeating "running".
    const dc = inputs.dimCycle ?? null;
    const runKnown = inputs.totalFiles > 0;
    const modeHint = inputs.scanMode === 'incremental' ? ' · changed since last scan'
      : inputs.scanMode === 'clean scan' ? ' · full rescan' : '';
    return [
      {
        label: dc ? `analyzing · dimension ${dc.index} / ${dc.count}` : 'analyzing',
        value: dc?.current ?? '—',
        hint: dc ? (dc.next ? `next: ${dc.next}` : (dc.count > 1 ? 'last dimension' : null)) : 'preparing…',
        tone: 'accent',
      },
      {
        label: 'files this run',
        value: runKnown ? inputs.takenFiles : '—',
        trailing: runKnown ? `/ ${inputs.totalFiles}` : null,
        hint: runKnown ? `${inputs.overallPct}%${modeHint}` : 'preparing…',
        tone: 'default',
      },
      foundCell(inputs.liveCount, 'violations', formatSevHint(inputs.sevCounts), inputs.suppressedCount, inputs.carriedCount),
      elapsedCell(inputs.elapsedS, 'elapsed', inputs.etaHint ?? null),
    ];
  }

  // failed / lost / cancelled — same shape as before, status-tone differs
  return [
    statusCell,
    progressCell(inputs),
    foundCell(inputs.liveCount, 'FOUND', 'live violations', inputs.suppressedCount, inputs.carriedCount),
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
