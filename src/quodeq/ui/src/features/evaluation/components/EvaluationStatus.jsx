import { useState } from 'react';
import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import ConsoleLogViewer from './ConsoleLogViewer.jsx';
import ScanProgress from './ScanProgress.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { CONSOLE_DOT_DISMISSED_KEY } from '../../../constants.js';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';

const STATUS = { RUNNING: 'running', DONE: 'done', FAILED: 'failed', LOST: 'lost' };
const DOT_OFFSET_TOP = -2;
const DOT_OFFSET_RIGHT = -4;

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

function phaseLabel(job) {
  if (!job || job.status !== STATUS.RUNNING) return null;
  switch (job.phase) {
    case 'setup': return 'Setting up';
    case 'analyzing': return 'Analyzing';
    case 'scoring': return 'Scoring';
    default: return 'Starting';
  }
}

const STATUS_MARKERS = { arrow: '\u2192', check: '\u2713', error: 'Error:', failed: 'failed' };

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

function ExternalRunBadge() {
  return (
    <div className="job-meta-item">
      <span className="job-meta-label">Source</span>
      <span className="job-meta-value">External</span>
    </div>
  );
}

function ConsolePanel({ job, consoleOpen, setConsoleOpen, hasEvaluations }) {
  const isRunning = job.status === STATUS.RUNNING;
  const isFailed = job.status === STATUS.FAILED;
  const isLost = job.status === STATUS.LOST;
  const [showDot, setShowDot] = useState(() => {
    if (hasEvaluations) return false;
    try { return !localStorage.getItem(CONSOLE_DOT_DISMISSED_KEY); } catch { return true; }
  });
  return (
    <>
      <div
        className="eval-status-row eval-status-row--clickable"
        role="button"
        tabIndex={0}
        onClick={() => { setConsoleOpen(o => !o); if (showDot) { setShowDot(false); try { localStorage.setItem(CONSOLE_DOT_DISMISSED_KEY, '1'); } catch {} } }}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setConsoleOpen(o => !o); } }}
        aria-label={consoleOpen ? 'Hide console' : 'Show console'}
      >
        {isRunning && <span className="eval-status-phase">{phaseLabel(job)}</span>}
        {isFailed && <span className="eval-status-phase eval-status-phase--error">{lastRelevantLog(job.logs) || 'Analysis failed'}</span>}
        {isLost && <span className="eval-status-phase eval-status-phase--error">Server restarted — job tracking lost</span>}
        {isRunning && job.dimensions?.length > 0 && (
          <span className="eval-status-dims">
            {job.dimensions.map(d => (
              <span key={d} className={`eval-dim-tag${d === job.currentDimension ? ' active' : ''}`}>{d}</span>
            ))}
          </span>
        )}
        <span className="eval-console-indicator" style={{ position: 'relative' }}>
          <svg className="eval-console-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="1" y="2" width="14" height="12" rx="2" />
            <polyline points="4.5,6.5 7,9 4.5,11.5" />
            <line x1="9" y1="11" x2="12" y2="11" />
          </svg>
          {consoleOpen ? '▾' : '▸'}
          {showDot && !consoleOpen && <span className="sidebar-nav-dot" style={{ top: DOT_OFFSET_TOP, right: DOT_OFFSET_RIGHT }} />}
        </span>
      </div>
      {consoleOpen && <ConsoleLogViewer logs={job.logs} />}
    </>
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
  const [consoleOpen, setConsoleOpen] = useState(false);

  if (!job) return null;

  return (
    <div className="panel evaluate-job-panel">
      <JobHeader job={job} onDismiss={onDismiss} onCancel={onCancel} />
      <JobMeta job={job} projectName={deriveProjectName(job.repo)} />
      <ScanProgress jobId={job.jobId} status={job.status} />
      <ConsolePanel job={job} consoleOpen={consoleOpen} setConsoleOpen={setConsoleOpen} hasEvaluations={hasEvaluations} />
      <LiveViolationsFeed liveViolations={liveViolations} />
    </div>
  );
}
