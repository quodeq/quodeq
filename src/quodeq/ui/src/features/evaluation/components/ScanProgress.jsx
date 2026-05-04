import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getEvaluationProgress } from '../../../api/index.js';
import { evaluationKeys } from '../../../api/queryKeys.js';
import { useEvalLog } from '../eval-log/EvalLogContext.js';
import { pct, computeOverallProgress } from './scanProgressTotals.js';
import ConsoleButton from '../../../components/ConsoleButton.jsx';

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATES = new Set(['done', 'failed', 'cancelled']);
const STATUS_MARKERS = { arrow: '\u2192', check: '\u2713', error: 'Error:', failed: 'failed' };

function formatClock(s) {
  if (s == null || !Number.isFinite(s)) return '—';
  const total = Math.max(0, Math.floor(s));
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

function isStatusLine(line) {
  const prefixes = [STATUS_MARKERS.arrow, STATUS_MARKERS.check, STATUS_MARKERS.error];
  return prefixes.some((p) => line.startsWith(p)) || line.includes(STATUS_MARKERS.failed);
}

function lastRelevantLog(logs) {
  if (!logs?.length) return null;
  for (let i = logs.length - 1; i >= 0; i--) {
    const line = logs[i].trim();
    if (isStatusLine(line)) return line;
  }
  return null;
}

// Reasons surfaced as a badge so an unusually large estimate isn't a mystery.
const ESTIMATE_REASON_LABEL = {
  'catching-up': 'catching up',
  'first-run': 'first run',
  'standards-changed': 'standards changed',
  'prompts-changed': 'prompts changed',
};

function DimRow({ dim }) {
  const taken = dim.files?.taken ?? 0;
  const isPending = dim.state === 'pending';
  // Backend supplies accurate per-dim totals: a precomputed estimate for
  // pending dims, the live queue size for running/done. A 0 here means
  // estimates haven't landed yet — render nothing rather than a guess.
  const total = dim.files?.total ?? 0;
  const reasonLabel = ESTIMATE_REASON_LABEL[dim.estimateReason];
  const reasonBadge = reasonLabel
    ? <> · <span className="scan-progress__dim-reason">{reasonLabel}</span></>
    : null;
  // When the dimension reports `done`, force the bar to 100% even if
  // `files.taken < files.total` (incremental skips, dismissed files, etc.).
  // Backend `done` is the source of truth — count drift shouldn't make a
  // green dimension look red.
  const isDone = dim.state === 'done';
  const isRunning = dim.state === 'running';
  const p = isDone ? 100 : pct(taken, total);

  let icon = '○';
  let iconClass = '';
  if (isDone) {
    icon = '✓';
    iconClass = 'scan-progress__dim-icon--done';
  } else if (isRunning) {
    icon = '▶';
    iconClass = 'scan-progress__dim-icon--running';
  }

  let meta;
  if (isPending) {
    meta = total > 0
      ? <span className="scan-progress__dim-meta-projected">0 / {total}{reasonBadge}</span>
      : <span className="scan-progress__dim-meta-projected">estimating…</span>;
  } else if (isDone) {
    meta = (
      <>
        {total > 0 ? `${taken} files` : ''}
        {dim.violations > 0 && <> · <span className="scan-progress__v">{dim.violations}v</span></>}
        {dim.compliance > 0 && <> · <span className="scan-progress__c">{dim.compliance}c</span></>}
        {dim.elapsedS != null && <> · {formatClock(dim.elapsedS)}</>}
      </>
    );
  } else {
    // Only show a clock segment when we actually have a number to print.
    // Without this guard, a running dim with no elapsed time yields a
    // dangling "· —" tail.
    let budgetPart = null;
    if (dim.budgetS) {
      const overrun = dim.elapsedS != null && dim.elapsedS > dim.budgetS;
      const cls = overrun ? 'scan-progress__budget scan-progress__budget--overrun' : 'scan-progress__budget';
      budgetPart = (
        <span className={cls}>
          {formatClock(dim.elapsedS)} / {formatClock(dim.budgetS)} budget
        </span>
      );
    } else if (dim.elapsedS != null) {
      budgetPart = <span className="scan-progress__budget">{formatClock(dim.elapsedS)}</span>;
    }
    meta = (
      <>
        {`${taken} / ${total}`}
        {reasonBadge}
        {dim.activeAgents > 0 && <> · {dim.activeAgents} agents</>}
        {dim.violations > 0 && <> · <span className="scan-progress__v">{dim.violations}v</span></>}
        {dim.compliance > 0 && <> · <span className="scan-progress__c">{dim.compliance}c</span></>}
        {budgetPart && <> · {budgetPart}</>}
      </>
    );
  }

  const fillClass = isDone ? 'scan-progress__bar-fill--done' : '';

  return (
    <div className={`scan-progress__dim${isPending ? ' scan-progress__dim--pending' : ''}`}>
      <span className={`scan-progress__dim-icon ${iconClass}`}>{icon}</span>
      <span className="scan-progress__dim-name">{dim.id}</span>
      <div className="scan-progress__bar">
        <div className={`scan-progress__bar-fill ${fillClass}`} style={{ width: `${p}%` }} />
      </div>
      <span className="scan-progress__dim-meta">{meta}</span>
    </div>
  );
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

  const progressQuery = useQuery({
    queryKey: jobId ? [...evaluationKeys.evaluation(jobId), 'progress'] : ['evaluation', '_none_', 'progress'],
    queryFn: () => getEvaluationProgress(jobId),
    enabled: !!jobId,
    refetchInterval: isTerminal ? false : POLL_INTERVAL_MS,
    staleTime: 0,
    retry: false,
  });
  // Best-effort: surface the last successful payload, ignore errors silently
  // (progress is purely informational and should never block the UI).
  const progress = progressQuery.data ?? null;

  useEffect(() => {
    if (evalLog.activeJobId === jobId) {
      evalLog.updateJobStatus(status);
    }
  }, [evalLog, jobId, status]);

  if (!jobId) return null;

  const dims = progress?.dimensions || [];
  const { totalFiles, takenFiles, overallPct } = computeOverallProgress(progress);
  const inlineLabel = progress?.currentDimension
    ? <>running <span className="scan-progress__dim-active">{progress.currentDimension}</span></>
    : progress?.phase
      ? <>phase: <span className="scan-progress__dim-active">{progress.phase}</span></>
      : null;

  function toggleDetail() {
    setDetailOpen((v) => !v);
  }
  function toggleConsole() {
    if (consoleOpen) {
      evalLog.closeLog();
    } else {
      evalLog.openLog(jobId, progress?.runId || null, status);
    }
  }

  // Failed / lost: show the error message inline above the progress bar.
  const errorBanner = isFailed
    ? <div className="scan-progress__error">{lastRelevantLog(job.logs) || 'Analysis failed'}</div>
    : isLost
      ? <div className="scan-progress__error">Server restarted — job tracking lost</div>
      : null;

  return (
    <div className="scan-progress">
      {errorBanner}
      <div className="scan-progress__row">
        <div className="scan-progress__bar-wrap">
          <div className="scan-progress__bar">
            <div className="scan-progress__bar-fill" style={{ width: `${overallPct}%` }} />
          </div>
          <div className="scan-progress__meta">
            <span>
              {totalFiles > 0 ? <><strong>{takenFiles} / {totalFiles}</strong> checks · {overallPct}%</> : <strong>preparing…</strong>}
              {isRunning && inlineLabel && <> · {inlineLabel}</>}
            </span>
            {progress?.totalElapsedS != null && (
              <span><strong>{formatClock(progress.totalElapsedS)}</strong> total</span>
            )}
          </div>
        </div>
        <div className="scan-progress__actions">
          <button
            type="button"
            className={`scan-progress__detail-toggle${detailOpen ? ' scan-progress__detail-toggle--open' : ''}`}
            onClick={toggleDetail}
            aria-expanded={detailOpen}
            aria-controls={`scan-progress-detail-${jobId}`}
            title={detailOpen ? 'Hide per-dimension detail' : 'Show per-dimension detail'}
          >
            <span className="scan-progress__detail-label">
              {/* Ghost label reserves the width of the longest label so the
                  button (and therefore the progress bar to its left) doesn't
                  reflow when toggling between "details" and "hide". */}
              <span className="scan-progress__detail-label-ghost" aria-hidden="true">details</span>
              <span className="scan-progress__detail-label-active">{detailOpen ? 'hide' : 'details'}</span>
            </span>
            <span className={`scan-progress__caret${detailOpen ? ' scan-progress__caret--open' : ''}`} aria-hidden="true">▸</span>
          </button>
          <ConsoleButton open={consoleOpen} onToggle={toggleConsole} />
        </div>
      </div>
      {detailOpen && dims.length > 0 && (
        <div className="scan-progress__expanded" id={`scan-progress-detail-${jobId}`}>
          <div className="scan-progress__expanded-label">Per-dimension</div>
          {dims.map((d) => <DimRow key={d.id} dim={d} />)}
        </div>
      )}
    </div>
  );
}
