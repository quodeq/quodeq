import { useEffect, useMemo } from 'react';
import { StatStrip, Stat } from '../../../components/terminal/index.js';
import { computeOverallProgress } from './scanProgressTotals.js';
import {
  buildJobStatCells, computeRate, buildEtaHint,
  buildDimensionCycle, sumSeverities, deriveScanMode,
} from './buildJobStatCells.js';
import { recordRateSample, getRateSamples } from './rateSampleStore.js';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';
import { useRunElapsed } from '../hooks/useRunElapsed.js';

const TERMINAL_STATES = new Set(['done', 'completed', 'failed', 'cancelled', 'lost']);

function sumLiveViolations(liveViolations) {
  if (!liveViolations) return 0;
  return Object.values(liveViolations).reduce((n, vs) => n + (vs?.length || 0), 0);
}

// The live feed already excludes dismissed/deleted findings (it reads the same
// filtered dimension evals the report does), so FOUND is a net number. The
// progress payload carries what was netted out, so the strip can say so.
// The parent (EvaluationStatus) may also have filtered out carried-forward
// findings before this component ever sees liveViolations, per the
// live-findings-only setting, so FOUND can be net of those too.
function sumSuppressed(progress) {
  return (progress?.dimensions || []).reduce((n, d) => n + (d?.suppressed || 0), 0);
}

// Current throughput from the persisted sliding window (null → "estimating…"
// until ~30s of samples accumulate). No whole-run average: it over-reads
// because the parallel start burst-completes cached files cheaply.
function computeJobStatCells({ jobId, job, progress, liveViolations, isTerminal, elapsedS, hiddenCarriedCount }) {
  if (!jobId) return [];
  const { takenFiles, totalFiles, overallPct } = computeOverallProgress(progress);
  const liveCount = sumLiveViolations(liveViolations);
  const rate = isTerminal ? null : computeRate(getRateSamples(jobId));
  const etaHint = isTerminal ? null : buildEtaHint({ rate, takenFiles, totalFiles });
  const suppressedCount = sumSuppressed(progress);
  return buildJobStatCells(job.status, {
    overallPct, takenFiles, totalFiles, elapsedS, liveCount, etaHint, suppressedCount,
    carriedCount: hiddenCarriedCount,
    exitReason: job.exitReason,
    dimCycle: buildDimensionCycle(progress),
    sevCounts: sumSeverities(liveViolations),
    scanMode: deriveScanMode(progress),
  });
}

export default function JobStatStrip({ job, liveViolations, hiddenCarriedCount = 0 }) {
  const jobId = job?.jobId;
  const isTerminal = TERMINAL_STATES.has(job?.status);

  const { data: progress, dataUpdatedAt } = useEvaluationProgress(jobId, isTerminal);
  // Server-anchored, per-second-ticking elapsed shared with ScanProgress, so
  // the ELAPSED tile and the footer clock always agree.
  const elapsedS = useRunElapsed(job, progress, dataUpdatedAt);

  // Throughput samples live in a module-level store (rateSampleStore.js) keyed
  // by jobId, so the sliding-window rate SURVIVES navigating out of and back
  // into a running job — re-entry shows the current rate immediately instead of
  // re-measuring from "estimating…". One sample per completed poll (keyed on
  // dataUpdatedAt, which advances every poll even when the data is identical, so
  // a stall registers as flat samples and reads as "estimating…").
  useEffect(() => {
    if (!progress || isTerminal) return;
    const { takenFiles, totalFiles } = computeOverallProgress(progress);
    if (!(totalFiles > 0)) return;
    recordRateSample(jobId, Date.now(), takenFiles);
  }, [dataUpdatedAt, isTerminal, progress, jobId]);

  const cells = useMemo(
    () => computeJobStatCells({ jobId, job, progress, liveViolations, isTerminal, elapsedS, hiddenCarriedCount }),
    // `elapsedS` advances once per second via useRunElapsed; the sample store is read (not a dep).
    [jobId, job?.status, job?.exitReason, isTerminal, progress, liveViolations, hiddenCarriedCount, elapsedS],
  );

  if (!jobId) return null;

  return (
    <div className="eval-job-stat-strip">
      <StatStrip cards>
        {cells.map((c) => (
          <Stat key={c.label} label={c.label} value={c.value} hint={c.hint} tone={c.tone} trailing={c.trailing} />
        ))}
      </StatStrip>
    </div>
  );
}
