import { useEffect, useMemo, useState } from 'react';
import { StatStrip, Stat } from '../../../components/terminal/index.js';
import { computeOverallProgress } from './scanProgressTotals.js';
import { buildJobStatCells, computeRate, buildEtaHint, msUntilNextSecond } from './buildJobStatCells.js';
import { recordRateSample, getRateSamples } from './rateSampleStore.js';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';

const TERMINAL_STATES = new Set(['done', 'completed', 'failed', 'cancelled', 'lost']);

function sumLiveViolations(liveViolations) {
  if (!liveViolations) return 0;
  return Object.values(liveViolations).reduce((n, vs) => n + (vs?.length || 0), 0);
}

// Live elapsed from wall-clock so the cell ticks every second between the 2s
// progress polls. Falls back to the backend-reported elapsed only when the job
// carries no usable startedAt.
function deriveElapsedS(startedAt, endedAt, isTerminal, fallbackElapsed) {
  if (startedAt) {
    const start = Date.parse(startedAt);
    if (!Number.isNaN(start)) {
      const end = isTerminal && endedAt ? Date.parse(endedAt) : Date.now();
      if (!Number.isNaN(end)) return Math.max(0, (end - start) / 1000);
    }
  }
  if (fallbackElapsed != null && Number.isFinite(fallbackElapsed)) return fallbackElapsed;
  return null;
}

export default function JobStatStrip({ job, liveViolations }) {
  const jobId = job?.jobId;
  const isTerminal = TERMINAL_STATES.has(job?.status);

  const { data: progress, dataUpdatedAt } = useEvaluationProgress(jobId, isTerminal);

  // Re-render aligned to each whole-second boundary of wall-clock elapsed, so
  // ELAPSED ticks *evenly*. A fixed setInterval(1000) has its phase fixed at
  // mount and beats against the second boundary as timer jitter drifts it,
  // producing visible double/skip ticks. A self-correcting timeout recomputes
  // the delay from absolute `now` each tick — it re-aligns to the boundary and
  // never accumulates drift. Inactive on terminal states / without a startedAt
  // (the elapsed value is then poll-derived and can't tick per-second anyway).
  const [tick, setTick] = useState(0);
  const startMs = job?.startedAt ? Date.parse(job.startedAt) : NaN;
  useEffect(() => {
    if (isTerminal || !jobId || Number.isNaN(startMs)) return undefined;
    let id;
    const schedule = () => {
      id = setTimeout(() => { setTick((t) => t + 1); schedule(); }, msUntilNextSecond(Date.now() - startMs));
    };
    schedule();
    return () => clearTimeout(id);
  }, [isTerminal, jobId, startMs]);

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

  const cells = useMemo(() => {
    if (!jobId) return [];
    const { takenFiles, totalFiles, overallPct } = computeOverallProgress(progress);
    const elapsedS = deriveElapsedS(job?.startedAt, job?.endedAt, isTerminal, progress?.totalElapsedS);
    const liveCount = sumLiveViolations(liveViolations);
    // Current throughput from the persisted sliding window (null → "estimating…"
    // until ~30s of samples accumulate). No whole-run average: it over-reads
    // because the parallel start burst-completes cached files cheaply.
    const rate = isTerminal ? null : computeRate(getRateSamples(jobId));
    const etaHint = isTerminal ? null : buildEtaHint({ rate, takenFiles, totalFiles });
    return buildJobStatCells(job.status, { overallPct, takenFiles, totalFiles, elapsedS, liveCount, etaHint });
    // `tick` drives the per-second recompute; the sample store is read (not a dep).
  }, [jobId, job?.status, job?.startedAt, job?.endedAt, isTerminal, progress, liveViolations, tick]);

  if (!jobId) return null;

  return (
    <div className="eval-job-stat-strip">
      <StatStrip cards>
        {cells.map((c) => (
          <Stat key={c.label} label={c.label} value={c.value} hint={c.hint} tone={c.tone} />
        ))}
      </StatStrip>
    </div>
  );
}
