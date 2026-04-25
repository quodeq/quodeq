import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import ScanProgress from './ScanProgress.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';

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

function ExternalRunBadge() {
  return (
    <div className="job-meta-item">
      <span className="job-meta-label">Source</span>
      <span className="job-meta-value">External</span>
    </div>
  );
}

function StatusChip({ status, exitReason }) {
  const isStale = status === 'cancelled' && typeof exitReason === 'string' && exitReason.startsWith('stale_');
  const text = isStale ? 'cancelled (stale)' : status;
  const className = `job-status-badge ${status}${isStale ? ' job-status-badge--stale' : ''}`;
  return (
    <span className={className} title={exitReason ?? ''}>
      {text}
    </span>
  );
}

function JobHeader({ job, onDismiss, onCancel }) {
  const isRunning = job.status === STATUS.RUNNING;
  const isDone = job.status === STATUS.DONE;
  return (
    <div className="job-header">
      <div className="job-header-left">
        <h3>{statusTitle(job.status)}</h3>
      </div>
      <div className="job-header-right">
        {isRunning && <button type="button" className="job-cancel-inline" onClick={onCancel}>Cancel</button>}
        {!isRunning && isDone && <button type="button" className="job-header-view-btn" onClick={() => onDismiss('view')}>View Results</button>}
        {!isRunning && <button type="button" className="job-header-dismiss-btn" onClick={() => onDismiss('close')}>{isDone ? 'Dismiss' : 'Close'}</button>}
        <StatusChip status={job.status} exitReason={job.exitReason} />
      </div>
    </div>
  );
}

function JobProviderBadge() {
  const provider = localStorage.getItem(ACTIVE_PROVIDER_KEY) || '';
  const model = localStorage.getItem(providerKey(provider, 'model')) || '';
  if (!provider) return null;
  return (
    <div className="job-meta-item">
      <span className="job-meta-label">AI Provider</span>
      <span className="job-meta-value">{provider}{model ? ` / ${model}` : ''}</span>
    </div>
  );
}

function JobMeta({ job, projectName }) {
  const isExternal = job.source === 'external';
  return (
    <div className="job-meta">
      {projectName && (
        <div className="job-meta-item">
          <span className="job-meta-label">Project</span>
          <span className="job-meta-value">{projectName}</span>
        </div>
      )}
      {isExternal ? <ExternalRunBadge /> : <JobProviderBadge />}
      <div className="job-meta-item">
        <span className="job-meta-label">Job ID</span>
        <div className="job-meta-id-row">
          <code className="job-meta-code job-meta-code--muted">{job.jobId}</code>
          <CopyButton aria-label="Copy job ID" onClick={() => copyToClipboard(job.jobId)} />
        </div>
      </div>
      {job.repo && (
        <div className="job-meta-item job-meta-item--full">
          <span className="job-meta-label">Repository</span>
          <code className="job-meta-code">{job.repo}</code>
        </div>
      )}
    </div>
  );
}

export default function EvaluationStatus({ job, liveViolations = {}, onDismiss, onCancel, hasEvaluations }) {
  if (!job) return null;

  return (
    <div className="panel evaluate-job-panel">
      <JobHeader job={job} onDismiss={onDismiss} onCancel={onCancel} />
      <JobMeta job={job} projectName={deriveProjectName(job.repo)} />
      <ScanProgress job={job} hasEvaluations={hasEvaluations} />
      <LiveViolationsFeed liveViolations={liveViolations} />
    </div>
  );
}
