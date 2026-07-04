/**
 * Math helpers for the live evaluation header.
 *
 * The header sums every dimension's file counts. Per-dim totals come from
 * the backend: pending dims carry a precomputed estimate (written before
 * any dim runs), running/done dims carry their actual queue total. This
 * keeps the header total stable from t=0 — no jumps as new dims start
 * and reveal their post-filter queue size.
 *
 * Until every pending dim has an estimate, the header reads "preparing…"
 * rather than printing a misleading partial sum. This covers the brief
 * window between status.json (state=running) and dim_estimates.json
 * landing on disk.
 *
 * The header additionally sums whole-project coverage (`filesCached` /
 * `filesProjectTotal` per dim) when every dim carries it; otherwise the
 * coverage fields are null and the UI falls back to the run-only display.
 */

export function pct(taken, total) {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((taken / total) * 100));
}

/**
 * Best estimate of a single-dim's file count: the largest queue total
 * observed among running/done dims. Falls back to `progress.projectFiles`
 * before any dim has started. Returns 0 if nothing is known.
 */
export function dimFileEstimate(progress) {
  const dims = progress?.dimensions || [];
  const observed = dims
    .filter((d) => d?.state !== 'pending')
    .map((d) => d?.files?.total ?? 0)
    .filter((n) => n > 0);
  if (observed.length > 0) return Math.max(...observed);
  return progress?.projectFiles ?? 0;
}

const NO_COVERAGE = { projectTotal: null, cachedFiles: null, coveredFiles: null, coveredPct: null };

export function computeOverallProgress(progress) {
  const dims = progress?.dimensions || [];
  if (dims.length === 0) {
    return { totalFiles: 0, takenFiles: 0, overallPct: 0, ...NO_COVERAGE };
  }

  // "preparing…" only when *nothing* is known yet — i.e. no dim has
  // started AND no pending dim has an estimate. Once any dim is
  // running/done or has a total, we show what we know rather than
  // contradicting an obviously-running run with a "preparing" label.
  const anyDimStarted = dims.some((d) => d?.state === 'running' || d?.state === 'done');
  const anyTotalKnown = dims.some((d) => (d?.files?.total ?? 0) > 0);
  if (!anyDimStarted && !anyTotalKnown) {
    return { totalFiles: 0, takenFiles: 0, overallPct: 0, ...NO_COVERAGE };
  }

  // Sum across dims using whatever total each one carries. Pending dims
  // with no estimate (total=0) contribute nothing — they'll join the
  // header sum once their estimate or queue lands.
  let takenFiles = 0;
  let totalFiles = 0;
  // Whole-project coverage (incremental runs): every dim must carry the
  // fields — a single legacy dim would make the sum lie, so it nulls out.
  let hasCoverage = true;
  let cachedFiles = 0;
  let projectTotal = 0;
  for (const d of dims) {
    takenFiles += d?.files?.taken ?? 0;
    totalFiles += d?.files?.total ?? 0;
    if (Number.isFinite(d?.filesCached) && Number.isFinite(d?.filesProjectTotal)) {
      cachedFiles += d.filesCached;
      projectTotal += d.filesProjectTotal;
    } else {
      hasCoverage = false;
    }
  }

  const coverage = hasCoverage
    ? {
        projectTotal,
        cachedFiles,
        // Estimate-time totals vs live queue counts can drift when files
        // change on disk mid-run; clamp so we never render "105 / 100".
        coveredFiles: Math.min(cachedFiles + takenFiles, projectTotal),
        coveredPct: pct(cachedFiles + takenFiles, projectTotal),
      }
    : NO_COVERAGE;

  return { totalFiles, takenFiles, overallPct: pct(takenFiles, totalFiles), ...coverage };
}
