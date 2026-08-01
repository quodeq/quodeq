import { useMemo } from 'react';
import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import ScanProgress from './ScanProgress.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { TermHeader } from '../../../components/terminal/index.js';
import JobStatStrip from './JobStatStrip.jsx';
import { IdentityStrip, IdentityCell } from './IdentityStrip.jsx';
import { deriveScanMode } from './buildJobStatCells.js';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';
import useLiveFeedSettings from '../../settings/hooks/useLiveFeedSettings.js';
import { exitReasonLabel, isTimeLimitExit } from '../../../models/exitReason.js';
import { t } from '../../../strings/index.js';
import { jobStatusLabel } from '../../../strings/labels.js';

const STATUS = { RUNNING: 'running', DONE: 'done', FAILED: 'failed', LOST: 'lost' };
const TERMINAL_STATES = new Set(['done', 'completed', 'failed', 'cancelled', 'lost']);

// A cancelled/failed job whose run hit its time budget is not an error:
// the header must agree with the coverage banner below it, which already
// says "time limit reached" from the run's status.json. Done runs keep
// their "complete" header; the banner tells the truncation story there.
function isTimeLimitEnd(status, exitReason) {
  return (status === 'cancelled' || status === STATUS.FAILED) && isTimeLimitExit(exitReason);
}

function termNameForStatus(status, exitReason) {
  if (status === STATUS.RUNNING) return t('evaluate.termInProgress');
  if (isTimeLimitEnd(status, exitReason)) return t('evaluate.termTimeLimit');
  if (status === STATUS.DONE)    return t('evaluate.termComplete');
  if (status === STATUS.FAILED)  return t('evaluate.termFailed');
  if (status === STATUS.LOST)    return t('evaluate.termLost');
  return t('evaluate.termCancelled');
}

function RunPill({ status, exitReason }) {
  const timeLimit = isTimeLimitEnd(status, exitReason);
  const mod = status === STATUS.RUNNING ? 'running'
    : status === STATUS.DONE ? 'done'
    : !timeLimit && (status === STATUS.FAILED || status === STATUS.LOST) ? 'failed'
    : 'neutral';
  return (
    <span className={`eval-run-pill eval-run-pill--${mod}`}>
      {status === STATUS.RUNNING && <span className="eval-run-pill__dot" aria-hidden="true" />}
      {timeLimit ? exitReasonLabel(exitReason) : jobStatusLabel(status)}
    </span>
  );
}

function JobHeader({ job, onDismiss, onCancel }) {
  const isRunning = job.status === STATUS.RUNNING;
  const isDone = job.status === STATUS.DONE;
  return (
    <div className="evaluate-panel__top evaluate-panel__top--row">
      <TermHeader
        name={termNameForStatus(job.status, job.exitReason)}
        badge={<RunPill status={job.status} exitReason={job.exitReason} />}
      />
      <div className="evaluate-panel__top-actions">
        {isRunning && (
          <button type="button" className="term-btn term-btn--ghost term-btn--sm" onClick={onCancel}>{t('evaluate.cancelBtn')}</button>
        )}
        {!isRunning && isDone && (
          <button type="button" className="term-btn term-btn--primary term-btn--sm" onClick={() => onDismiss('view')}>
            <span aria-hidden="true">▸</span> {t('evaluate.viewResults')}
          </button>
        )}
        {!isRunning && (
          <button type="button" className="term-btn term-btn--secondary term-btn--sm" onClick={() => onDismiss('close')}>{t('evaluate.closeBtn')}</button>
        )}
      </div>
    </div>
  );
}

function JobIdentityStrip({ job, projectLabel }) {
  const isTerminal = TERMINAL_STATES.has(job.status);
  // Shares the strip/progress query cache entry — no extra polling.
  const { data: progress } = useEvaluationProgress(job.jobId, isTerminal);
  const mode = deriveScanMode(progress);
  return (
    <IdentityStrip>
      {/* "Unknown beats wrong": a dash, never the global selection. */}
      <IdentityCell label={t('evaluate.idRepository')}>{projectLabel ?? '—'}</IdentityCell>
      <IdentityCell label={t('evaluate.idJobId')} grow title={job.jobId}>
        <code className="eval-identity__code">{job.jobId}</code>
        <CopyButton aria-label={t('evaluate.copyJobIdAria')} onClick={() => copyToClipboard(job.jobId)} />
      </IdentityCell>
      {job.aiProvider && job.aiModel && (
        <IdentityCell label={t('evaluate.idModel')}>
          <span data-testid="job-runtime-chip">
            {job.aiProvider}
            <span className="eval-provider-sep" aria-hidden="true"> · </span>
            {job.aiModel}
          </span>
        </IdentityCell>
      )}
      <IdentityCell label={t('evaluate.idMode')}>{mode ?? '—'}</IdentityCell>
    </IdentityStrip>
  );
}

export default function EvaluationStatus({ job, jobProjectInfo, startedProjectInfo, liveViolations = {}, onDismiss, onCancel, hasEvaluations }) {
  const { newOnly } = useLiveFeedSettings();
  // Filter ONCE, above both consumers. JobStatStrip derives its violations
  // cell from the same object the feed lists, so filtering in each child
  // separately is how the counter and the list drift apart (see #878).
  const { shown, hiddenCarriedCount } = useMemo(() => {
    if (!newOnly) return { shown: liveViolations, hiddenCarriedCount: 0 };
    const next = {};
    let hidden = 0;
    for (const [dim, vs] of Object.entries(liveViolations || {})) {
      // The SSE stream (VITE_USE_SSE_EVENTS) writes raw wire payloads
      // straight into the findings cache with no violation-model mapping,
      // so those entries carry snake_case `carried_forward` instead of
      // `carriedForward`. Accept both spellings here.
      const fresh = (vs || []).filter((v) => !(v.carriedForward ?? v.carried_forward));
      hidden += (vs || []).length - fresh.length;
      if (fresh.length) next[dim] = fresh;
    }
    return { shown: next, hiddenCarriedCount: hidden };
  }, [liveViolations, newOnly]);

  if (!job) return null;
  // Prefer the running job's own project so the card stays accurate when the
  // UI's global selection points at a different project than the job is
  // actually scanning. Before the report-path marker resolves it, fall back
  // to the project the job was STARTED for. Never fall back to the global
  // selection: switching projects mid-run would mislabel a running
  // evaluation with a project it never touched. Unknown beats wrong.
  const jobProjectLabel = jobProjectInfo?.displayName || jobProjectInfo?.name || null;
  const startedLabel = startedProjectInfo?.displayName || startedProjectInfo?.name || null;
  const projectLabel = jobProjectLabel || startedLabel || null;

  return (
    <div className="panel evaluate-panel--terminal">
      <JobHeader job={job} onDismiss={onDismiss} onCancel={onCancel} />
      <JobIdentityStrip job={job} projectLabel={projectLabel} />
      <JobStatStrip job={job} liveViolations={shown} hiddenCarriedCount={hiddenCarriedCount} />
      <ScanProgress job={job} hasEvaluations={hasEvaluations} />
      <LiveViolationsFeed job={job} liveViolations={shown} hiddenCarriedCount={hiddenCarriedCount} />
    </div>
  );
}
