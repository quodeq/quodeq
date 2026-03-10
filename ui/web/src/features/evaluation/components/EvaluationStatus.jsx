import { useEffect, useRef, useState } from 'react';
import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import CopyButton from '../../../components/CopyButton.jsx';

function deriveProjectName(repo) {
  if (!repo) return null;
  return repo.replace(/\.git$/, '').split(/[/\\]/).filter(Boolean).pop() || null;
}

function statusTitle(status) {
  if (status === 'running') return 'Evaluation in Progress';
  if (status === 'done') return 'Evaluation Complete';
  if (status === 'failed') return 'Evaluation Failed';
  return 'Evaluation Cancelled';
}

function phaseLabel(job) {
  if (!job || job.status !== 'running') return null;
  switch (job.phase) {
    case 'setup': return 'Setting up';
    case 'analyzing': return 'Analyzing';
    case 'scoring': return 'Scoring';
    default: return 'Starting';
  }
}

export default function EvaluationStatus({ job, liveViolations = {}, onDismiss, onCancel }) {
  const logViewerRef = useRef(null);
  const [consoleOpen, setConsoleOpen] = useState(false);

  function lastRelevantLog(logs) {
    if (!logs?.length) return null;
    for (let i = logs.length - 1; i >= 0; i--) {
      const line = logs[i].trim();
      if (line.startsWith('→') || line.startsWith('✓') || line.startsWith('Error:') || line.includes('failed')) return line;
    }
    return null;
  }

  useEffect(() => {
    if (logViewerRef.current) {
      logViewerRef.current.scrollTop = logViewerRef.current.scrollHeight;
    }
  }, [job?.logs]);



  if (!job) return null;

  const isRunning = job.status === 'running';
  const isDone = job.status === 'done';
  const isFailed = job.status === 'failed';
  const projectName = deriveProjectName(job.repo);

  return (
    <div className="panel evaluate-job-panel">
      <div className="job-header">
        <div className="job-header-left">
          <h3>{statusTitle(job.status)}</h3>
        </div>
        <div className="job-header-right">
          {isRunning && (
            <button type="button" className="job-cancel-inline" onClick={onCancel}>
              Cancel
            </button>
          )}
          <span className={`job-status-badge ${job.status}`}>{job.status}</span>
        </div>
      </div>

      <div className="job-meta">
        {projectName && (
          <div className="job-meta-item">
            <span className="job-meta-label">Project</span>
            <span className="job-meta-value">{projectName}</span>
          </div>
        )}
        <div className="job-meta-item">
          <span className="job-meta-label">Job ID</span>
          <div className="job-meta-id-row">
            <code className="job-meta-code job-meta-code--muted">{job.jobId}</code>
            <CopyButton onClick={() => navigator.clipboard.writeText(job.jobId)} />
          </div>
        </div>
        {job.repo && (
          <div className="job-meta-item job-meta-item--full">
            <span className="job-meta-label">Repository</span>
            <code className="job-meta-code">{job.repo}</code>
          </div>
        )}
      </div>

      <div
        className="eval-status-row eval-status-row--clickable"
        role="button"
        tabIndex={0}
        onClick={() => setConsoleOpen(o => !o)}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setConsoleOpen(o => !o); } }}
        title={consoleOpen ? 'Hide console' : 'Show console'}
      >
        {isRunning && <span className="eval-status-phase">{phaseLabel(job)}</span>}
        {isFailed && <span className="eval-status-phase eval-status-phase--error">{lastRelevantLog(job.logs) || 'Analysis failed'}</span>}
        {isRunning && job.dimensions?.length > 0 && (
          <span className="eval-status-dims">
            {job.dimensions.map(d => (
              <span key={d} className={`eval-dim-tag${d === job.currentDimension ? ' active' : ''}`}>{d}</span>
            ))}
          </span>
        )}
        <span className="eval-console-indicator">
          <svg className="eval-console-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="1" y="2" width="14" height="12" rx="2" />
            <polyline points="4.5,6.5 7,9 4.5,11.5" />
            <line x1="9" y1="11" x2="12" y2="11" />
          </svg>
          {consoleOpen ? '▾' : '▸'}
        </span>
      </div>
      {consoleOpen && (
        <div className="console-output">
          <pre ref={logViewerRef}>
            {job.logs?.length ? job.logs.join('\n') : 'Waiting for output…'}
          </pre>
        </div>
      )}

      {!isRunning && (
        <div className="job-actions">
          {isDone && (
            <button className="view-results-btn" onClick={() => onDismiss('view')}>
              View Results
            </button>
          )}
          <button className="job-close-btn" onClick={() => onDismiss('close')}>
            {isDone ? 'Dismiss' : 'Close'}
          </button>
        </div>
      )}

      <LiveViolationsFeed liveViolations={liveViolations} />
    </div>
  );
}
