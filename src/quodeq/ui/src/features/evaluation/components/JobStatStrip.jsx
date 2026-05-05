import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEvaluationProgress } from '../../../api/index.js';
import { evaluationKeys } from '../../../api/queryKeys.js';
import { StatStrip, Stat } from '../../../components/terminal/index.js';
import { computeOverallProgress } from './scanProgressTotals.js';
import { buildJobStatCells } from './buildJobStatCells.js';

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATES = new Set(['done', 'completed', 'failed', 'cancelled', 'lost']);

function sumLiveViolations(liveViolations) {
  if (!liveViolations) return 0;
  return Object.values(liveViolations).reduce((n, vs) => n + (vs?.length || 0), 0);
}

export default function JobStatStrip({ job, liveViolations }) {
  const jobId = job?.jobId;
  const isTerminal = TERMINAL_STATES.has(job?.status);

  const { data: progress } = useQuery({
    queryKey: jobId ? [...evaluationKeys.evaluation(jobId), 'progress'] : ['evaluation', '_none_', 'progress'],
    queryFn: () => getEvaluationProgress(jobId),
    enabled: !!jobId,
    refetchInterval: isTerminal ? false : POLL_INTERVAL_MS,
    staleTime: 0,
    retry: false,
  });

  const cells = useMemo(() => {
    if (!jobId) return [];
    const { takenFiles, totalFiles, overallPct } = computeOverallProgress(progress);
    const elapsedS = progress?.totalElapsedS;
    const liveCount = sumLiveViolations(liveViolations);
    return buildJobStatCells(job.status, { overallPct, takenFiles, totalFiles, elapsedS, liveCount });
  }, [jobId, job?.status, progress, liveViolations]);

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
