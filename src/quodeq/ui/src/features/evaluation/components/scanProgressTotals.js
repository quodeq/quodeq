/**
 * Math helpers for the live evaluation header.
 *
 * The header tracks ONE dimension at a time — the currently-running one.
 * Multi-dim incremental scans have wildly different cache hit rates per
 * dim, so summing taken/total across dims produces a moving total that
 * jumps as each dim reveals its real (post-filter) queue size. Showing
 * the running dim's progress directly avoids that whiplash; the
 * per-dimension breakdown lives under the DETAILS toggle.
 *
 * Dim selection (in order):
 *   1. `progress.currentDimension` matches a dim → that one
 *   2. Else first dim where `state === 'running'` (race coverage)
 *   3. Else last dim where `state === 'done'` (so completed runs read 100%
 *      instead of 0/0)
 *   4. Else all zeros (setup phase / nothing started yet)
 *
 * `dimFileEstimate` is unchanged and still drives the per-dim row's
 * pending-dim projection inside the DETAILS panel.
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
  if (dims.length === 0) {
    return { totalFiles: 0, takenFiles: 0, overallPct: 0 };
  }

  const currentId = progress?.currentDimension;
  let dim = null;
  if (currentId) {
    dim = dims.find((d) => d?.id === currentId) || null;
  }
  if (!dim) {
    dim = dims.find((d) => d?.state === 'running') || null;
  }
  if (!dim) {
    // Walk from the end so we pick the most recently completed dim.
    for (let i = dims.length - 1; i >= 0; i--) {
      if (dims[i]?.state === 'done') {
        dim = dims[i];
        break;
      }
    }
  }
  if (!dim) {
    return { totalFiles: 0, takenFiles: 0, overallPct: 0 };
  }

  const takenFiles = dim.files?.taken ?? 0;
  const totalFiles = dim.files?.total ?? 0;
  return { totalFiles, takenFiles, overallPct: pct(takenFiles, totalFiles) };
}
