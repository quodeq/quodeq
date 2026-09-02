/**
 * Pure formatting/derivation helpers for the live evaluation stat strip
 * (`JobStatStrip`). No React, no network, no DOM — drop-in testable.
 */

import { computeOverallProgress } from '../scanProgressTotals.js';
import { t } from '../../../../strings/index.js';

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

/**
 * One elapsed value for the whole evaluate screen, anchored to the SERVER's
 * clock. The progress payload reports totalElapsedS computed from the run's
 * own status.json timestamps; the client only extrapolates forward by the
 * time since that payload landed. Anchoring to the server (instead of
 * Date.parse(job.startedAt) vs client Date.now()) makes the clock immune to
 * client/server clock skew and keeps every clock on the screen in lock-step
 * — the stat strip and the footer previously mixed client wall-clock with
 * 2s-stale poll data and visibly disagreed.
 *
 * Fallback order when the server hasn't reported an elapsed yet (first
 * render before any poll, legacy runs): job wall-clock timestamps, else null.
 * Non-running jobs freeze on the server value (or startedAt→endedAt).
 *
 * @param {object} args
 * @param {boolean} args.running
 * @param {number|null|undefined} args.serverElapsedS — progress.totalElapsedS
 * @param {number|null|undefined} args.serverUpdatedAtMs — when that payload landed (epoch ms)
 * @param {number} args.nowMs
 * @param {string|null|undefined} args.startedAt — ISO, fallback only
 * @param {string|null|undefined} args.endedAt — ISO, fallback only
 * @returns {number|null} seconds
 */
export function deriveRunElapsedS({ running, serverElapsedS, serverUpdatedAtMs, nowMs, startedAt, endedAt }) {
  if (Number.isFinite(serverElapsedS)) {
    if (!running) return serverElapsedS;
    const sinceMs = Number.isFinite(serverUpdatedAtMs) ? Math.max(0, nowMs - serverUpdatedAtMs) : 0;
    return serverElapsedS + sinceMs / 1000;
  }
  const start = startedAt ? Date.parse(startedAt) : NaN;
  if (Number.isNaN(start)) return null;
  const end = !running && endedAt ? Date.parse(endedAt) : nowMs;
  if (Number.isNaN(end)) return null;
  return Math.max(0, (end - start) / 1000);
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
 *
 * Returns an identity value ('incremental' | 'clean'), never display text:
 * callers compare it, and the words a user sees come from the catalog.
 */
export function deriveScanMode(progress) {
  if (!progress) return null;
  const { cachedFiles, projectTotal } = computeOverallProgress(progress);
  if (cachedFiles == null || !(projectTotal > 0)) return null;
  return cachedFiles > 0 ? 'incremental' : 'clean';
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
  return t('evaluate.carriedForward', { count: carriedCount });
}
