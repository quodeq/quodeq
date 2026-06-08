import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEvaluationProgress } from '../../../api/index.js';
import { evaluationKeys } from '../../../api/queryKeys.js';
import { StatStrip, Stat } from '../../../components/terminal/index.js';
import { computeOverallProgress } from './scanProgressTotals.js';
import { buildJobStatCells, computeRate, buildEtaHint, RATE_WINDOW_MS } from './buildJobStatCells.js';

const POLL_INTERVAL_MS = 2000;
const TICK_INTERVAL_MS = 1000;
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

  const { data: progress, dataUpdatedAt } = useQuery({
    queryKey: jobId ? [...evaluationKeys.evaluation(jobId), 'progress'] : ['evaluation', '_none_', 'progress'],
    queryFn: () => getEvaluationProgress(jobId),
    enabled: !!jobId,
    refetchInterval: isTerminal ? false : POLL_INTERVAL_MS,
    staleTime: 0,
    retry: false,
  });

  // Per-second re-render so wall-clock elapsed advances between the 2s polls.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (isTerminal || !jobId) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), TICK_INTERVAL_MS);
    return () => clearInterval(id);
  }, [isTerminal, jobId]);

  // Throughput samples: one per completed poll (keyed on dataUpdatedAt, which
  // advances every poll even when the data is identical — so a stall registers
  // as flat samples). Trimmed to RATE_WINDOW_MS. Kept in a ref so pushes don't
  // trigger renders; the 1s tick picks the new sample up within a second.
  const samplesRef = useRef([]);
  useEffect(() => { samplesRef.current = []; }, [jobId]);
  useEffect(() => {
    if (!progress || isTerminal) return;
    const { takenFiles, totalFiles } = computeOverallProgress(progress);
    if (!(totalFiles > 0)) return;
    const now = Date.now();
    const buf = samplesRef.current;
    buf.push({ t: now, taken: takenFiles });
    while (buf.length > 1 && now - buf[0].t > RATE_WINDOW_MS) buf.shift();
  }, [dataUpdatedAt, isTerminal, progress]);

  const cells = useMemo(() => {
    if (!jobId) return [];
    const { takenFiles, totalFiles, overallPct } = computeOverallProgress(progress);
    const elapsedS = deriveElapsedS(job?.startedAt, job?.endedAt, isTerminal, progress?.totalElapsedS);
    const liveCount = sumLiveViolations(liveViolations);
    const rate = isTerminal ? null : computeRate(samplesRef.current);
    const etaHint = isTerminal ? null : buildEtaHint({ rate, takenFiles, totalFiles });
    return buildJobStatCells(job.status, { overallPct, takenFiles, totalFiles, elapsedS, liveCount, etaHint });
    // `tick` drives the per-second recompute; samplesRef is read (not a dep).
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
