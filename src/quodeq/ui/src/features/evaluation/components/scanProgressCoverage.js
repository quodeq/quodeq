/**
 * Coverage / pct-width math for ScanProgress's header bar.
 *
 * Extracted verbatim out of ScanProgress.jsx: the invariant comments below
 * are load-bearing (see cachedPctWidth/runPctWidth), so the formulas are
 * unchanged from the pre-split version.
 */
import { computeOverallProgress } from './scanProgressTotals.js';

export function computeCoverageView(progress) {
  const { totalFiles, takenFiles, overallPct, projectTotal, cachedFiles, coveredFiles, coveredPct, excludedFiles } =
    computeOverallProgress(progress);
  // Segmented coverage view only when there is actually a cached portion to
  // show — full scans and legacy runs keep the familiar run-only display.
  const showCoverage = projectTotal > 0 && cachedFiles > 0;
  // coveredFiles is clamped to projectTotal upstream, so these widths can
  // never sum past 100 even when live queue counts drift from the estimate.
  // cachedPctWidth alone also can't exceed 100: the producer (_dim_estimates.py)
  // guarantees per-dim cached <= total, so summed cachedFiles <= projectTotal.
  const cachedPctWidth = showCoverage ? (cachedFiles / projectTotal) * 100 : 0;
  const runPctWidth = showCoverage ? ((coveredFiles - cachedFiles) / projectTotal) * 100 : 0;
  return {
    totalFiles, takenFiles, overallPct, projectTotal, cachedFiles, coveredFiles, coveredPct, excludedFiles,
    showCoverage, cachedPctWidth, runPctWidth,
  };
}

// The time limit is one deadline for the whole run, shared across all
// selected dimensions — so the countdown pairs total elapsed with the
// run-level budget. Overrun can show briefly: the watchdog allows a short
// grace past the deadline before killing the job.
export function computeRunBudget(progress, elapsedS) {
  const runBudgetS = progress?.budgetS;
  const overrun = runBudgetS > 0 && elapsedS > runBudgetS;
  return { runBudgetS, overrun };
}
