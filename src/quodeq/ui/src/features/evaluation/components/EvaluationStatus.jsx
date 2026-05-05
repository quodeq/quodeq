import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import ScanProgress from './ScanProgress.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';
import { TermHeader } from '../../../components/terminal/index.js';
import JobStatStrip from './JobStatStrip.jsx';

const STATUS = { RUNNING: 'running', DONE: 'done', FAILED: 'failed', LOST: 'lost' };

function deriveProjectName(repo) {
  if (!repo) return null;
  return repo.replace(/\.git$/, '').split(/[/\\]/).filter(Boolean).pop() || null;
}

function statusTitle(status) {
  if (status === STATUS.RUNNING) return 'Evaluation in Progress';
  if (status === STATUS.DONE) return 'Evaluation Complete';
  if (status === STATUS.FAILED) return 'Evaluation Failed';
  if (status === STATUS.LOST) return 'Evaluation Lost';
  return 'Evaluation Cancelled';
}

function termNameForStatus(status) {
  if (status === STATUS.RUNNING) return 'evaluation_in_progress';
  if (status === STATUS.DONE)    return 'evaluation_complete';
  if (status === STATUS.FAILED)  return 'evaluation_failed';
  if (status === STATUS.LOST)    return 'evaluation_lost';
  return 'evaluation_cancelled';
}

function ExternalRunBadge() {
  return (
    <div className="term-meta-grid__item">
      <span className="term-meta-grid__label">Source</span>
      <span className="term-meta-grid__value">External</span>
    </div>
  );
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

function JobProviderBadge() {
  const provider = localStorage.getItem(ACTIVE_PROVIDER_KEY) || '';
  const model = localStorage.getItem(providerKey(provider, 'model')) || '';
  if (!provider) return null;
  return (
    <div className="term-meta-grid__item">
      <span className="term-meta-grid__label">AI Provider</span>
      <span className="term-meta-grid__value">{provider}{model ? ` / ${model}` : ''}</span>
    </div>
  );
}

function JobHeader({ job, onDismiss, onCancel }) {
  const isRunning = job.status === STATUS.RUNNING;
  const isDone = job.status === STATUS.DONE;
  return (
    <div className="evaluate-panel__top evaluate-panel__top--row">
      <TermHeader name={termNameForStatus(job.status)} />
      <div className="evaluate-panel__top-actions">
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
        <StatusPill status={job.status} exitReason={job.exitReason} />
      </div>
    </div>
  );
}

function JobMeta({ job, projectName }) {
  const isExternal = job.source === 'external';
  return (
    <div className="term-meta-grid">
      {projectName && (
        <div className="term-meta-grid__item">
          <span className="term-meta-grid__label">Project</span>
          <span className="term-meta-grid__value">{projectName}</span>
        </div>
      )}
      {isExternal ? <ExternalRunBadge /> : <JobProviderBadge />}
      <div className="term-meta-grid__item">
        <span className="term-meta-grid__label">Job ID</span>
        <div className="term-meta-grid__value">
          <code>{job.jobId}</code>
          <CopyButton aria-label="Copy job ID" onClick={() => copyToClipboard(job.jobId)} />
        </div>
      </div>
      {job.repo && (
        <div className="term-meta-grid__item term-meta-grid__item--full">
          <span className="term-meta-grid__label">Repository</span>
          <code className="term-meta-grid__value">{job.repo}</code>
        </div>
      )}
    </div>
  );
}

export default function EvaluationStatus({ job, liveViolations = {}, onDismiss, onCancel, hasEvaluations }) {
  if (!job) return null;

  return (
    <div className="panel evaluate-panel--terminal">
      <JobHeader job={job} onDismiss={onDismiss} onCancel={onCancel} />
      <JobStatStrip job={job} liveViolations={liveViolations} />
      <JobMeta job={job} projectName={deriveProjectName(job.repo)} />
      <ScanProgress job={job} hasEvaluations={hasEvaluations} />
      <LiveViolationsFeed liveViolations={liveViolations} />
    </div>
  );
}
