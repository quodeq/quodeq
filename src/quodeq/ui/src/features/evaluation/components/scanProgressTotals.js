/**
 * Math helpers for the live evaluation header.
 *
 * The header shows the *aggregated* work across every dim: 2 dims × 100
 * files of analysis = "0 / 200 files" at start. That matches what the
 * dashboard is actually doing — analyse each file once per dim.
 *
 * Per-dim totals from `/api/evaluations/<jobId>/progress` are NOT
 * uniform at runtime, though: running/done dims report their post-filter
 * queue size while a pending dim falls back to the project-wide ceiling
 * (see `services/scan_progress.py`). Summing them as-is inflates the
 * headline by ~N× project_files in mixed states.
 *
 * `computeOverallProgress` substitutes a pending-dim's project-ceiling
 * total with the largest *observed* (running or done) queue total — the
 * same fallback the per-dim row uses — so every dim contributes a
 * consistent estimate. Once any dim has started, the fallback is the
 * actual filtered queue size; before that, it falls back to
 * `progress.projectFiles` as a last resort.
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

export function computeOverallProgress(progress) {
  const dims = progress?.dimensions || [];
  const dimEstimate = dimFileEstimate(progress);

  const totalFiles = dims.reduce((acc, d) => {
    // Pending dims expose the project-wide ceiling, not the post-filter
    // queue they'll actually scan. Swap in the fallback estimate so each
    // pending dim contributes a comparable number to the aggregate.
    if (d?.state === 'pending') return acc + dimEstimate;
    return acc + (d?.files?.total ?? 0);
  }, 0);
  const takenFiles = dims.reduce((acc, d) => acc + (d?.files?.taken ?? 0), 0);
  const overallPct = pct(takenFiles, totalFiles);

  return { totalFiles, takenFiles, overallPct };
}
