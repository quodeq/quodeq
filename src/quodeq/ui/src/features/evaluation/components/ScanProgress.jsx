import { useEffect, useState } from 'react';
import { useEvalLog } from '../eval-log/EvalLogContext.js';
import { ScanProgressBody } from './ScanProgressParts.jsx';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';
import { useRunElapsed } from '../hooks/useRunElapsed.js';

const TERMINAL_STATES = new Set(['done', 'failed', 'cancelled']);

function useSyncEvalLogStatus(evalLog, jobId, status) {
  useEffect(() => {
    if (evalLog.activeJobId === jobId) {
      evalLog.updateJobStatus(status);
    }
  }, [evalLog, jobId, status]);
}

function makeToggleConsole({ consoleOpen, evalLog, jobId, status, progress }) {
  return () => {
    if (consoleOpen) {
      evalLog.closeLog();
    } else {
      evalLog.openLog(jobId, progress?.runId || null, status);
    }
  };
}

export default function ScanProgress({ job, hasEvaluations = false }) {
  const jobId = job?.jobId;
  const status = job?.status;
  const isRunning = status === 'running';
  const isFailed = status === 'failed';
  const isLost = status === 'lost';

  const [detailOpen, setDetailOpen] = useState(false);
  const evalLog = useEvalLog();
  const consoleOpen = evalLog.activeJobId === jobId;
  const isTerminal = TERMINAL_STATES.has(status);

  const progressQuery = useEvaluationProgress(jobId, isTerminal);
  // Best-effort: surface the last successful payload, ignore errors silently
  // (progress is purely informational and should never block the UI).
  const progress = progressQuery.data ?? null;
  // Same server-anchored ticking clock the stat strip shows, so the footer
  // total can never disagree with the ELAPSED tile.
  const elapsedS = useRunElapsed(job, progress, progressQuery.dataUpdatedAt);

  useSyncEvalLogStatus(evalLog, jobId, status);

  if (!jobId) return null;

  const toggleConsole = makeToggleConsole({ consoleOpen, evalLog, jobId, status, progress });

  return (
    <ScanProgressBody
      job={job}
      status={status}
      isRunning={isRunning}
      isFailed={isFailed}
      isLost={isLost}
      progress={progress}
      elapsedS={elapsedS}
      detailOpen={detailOpen}
      toggleDetail={() => setDetailOpen((v) => !v)}
      consoleOpen={consoleOpen}
      toggleConsole={toggleConsole}
      jobId={jobId}
    />
  );
}
