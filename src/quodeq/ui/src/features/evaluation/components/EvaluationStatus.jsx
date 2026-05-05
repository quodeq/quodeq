import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import ScanProgress from './ScanProgress.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { TermHeader } from '../../../components/terminal/index.js';
import JobStatStrip from './JobStatStrip.jsx';

const STATUS = { RUNNING: 'running', DONE: 'done', FAILED: 'failed', LOST: 'lost' };

function termNameForStatus(status) {
  if (status === STATUS.RUNNING) return 'evaluation_in_progress';
  if (status === STATUS.DONE)    return 'evaluation_complete';
  if (status === STATUS.FAILED)  return 'evaluation_failed';
  if (status === STATUS.LOST)    return 'evaluation_lost';
  return 'evaluation_cancelled';
}

function StatusPill({ status, exitReason }) {
  const isStale = status === 'cancelled' && typeof exitReason === 'string' && exitReason.startsWith('stale_');
  const text = isStale ? 'cancelled (stale)' : status;
  const className = `term-status-pill term-status-pill--${status}${isStale ? ' term-status-pill--stale' : ''}`;
  return (
    <span className={className} title={exitReason ?? ''}>
      {text}
    </span>
  );
}

function ActionsHelp() {
  return (
    <HelpHint label="Job actions help">
      <div><strong>Cancel</strong> — stop the running evaluation.</div>
      <div><strong>View Results</strong> — open the completed run's full report.</div>
      <div><strong>Close</strong> — dismiss this panel without affecting the run.</div>
    </HelpHint>
  );
}

function JobHeader({ job, onDismiss, onCancel }) {
  const isRunning = job.status === STATUS.RUNNING;
  const isDone = job.status === STATUS.DONE;
  return (
    <div className="evaluate-panel__top evaluate-panel__top--row">
      <TermHeader name={termNameForStatus(job.status)} />
      <div className="evaluate-panel__top-actions">
        <ActionsHelp />
        {isRunning && (
          <button type="button" className="term-btn term-btn--ghost" onClick={onCancel}>cancel</button>
        )}
        {!isRunning && isDone && (
          <button type="button" className="term-btn term-btn--primary" onClick={() => onDismiss('view')}>
            <span aria-hidden="true">▸</span> view results
          </button>
        )}
        {!isRunning && (
          <button type="button" className="term-btn term-btn--secondary" onClick={() => onDismiss('close')}>close</button>
        )}
        {!isRunning && <StatusPill status={job.status} exitReason={job.exitReason} />}
      </div>
    </div>
  );
}

function JobIdLine({ jobId }) {
  return (
    <div className="evaluate-job-id-line">
      <span className="evaluate-job-id-line__label">job</span>
      <code>{jobId}</code>
      <CopyButton aria-label="Copy job ID" onClick={() => copyToClipboard(jobId)} />
    </div>
  );
}

export default function EvaluationStatus({ job, liveViolations = {}, onDismiss, onCancel, hasEvaluations }) {
  if (!job) return null;

  return (
    <div className="panel evaluate-panel--terminal">
      <JobHeader job={job} onDismiss={onDismiss} onCancel={onCancel} />
      <JobStatStrip job={job} liveViolations={liveViolations} />
      <JobIdLine jobId={job.jobId} />
      <ScanProgress job={job} hasEvaluations={hasEvaluations} />
      <LiveViolationsFeed liveViolations={liveViolations} />
    </div>
  );
}
