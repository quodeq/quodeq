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

export default function EvaluationStatus({ job, liveViolations = {}, onDismiss, onCancel }) {
  const logViewerRef = useRef(null);
  const [consoleOpen, setConsoleOpen] = useState(false);

  function lastRelevantLog(logs) {
    if (!logs?.length) return null;
    for (let i = logs.length - 1; i >= 0; i--) {
      const line = logs[i].trim();
      if (line.startsWith('→') || line.startsWith('✓')) return line;
    }
    return null;
  }

  useEffect(() => {
    if (logViewerRef.current) {
      logViewerRef.current.scrollTop = logViewerRef.current.scrollHeight;
    }
  }, [job?.logs]);

  useEffect(() => {
    setConsoleOpen(false);
  }, [job?.jobId]);

  if (!job) return null;

  const isRunning = job.status === 'running';
  const isDone = job.status === 'done';
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

      {isRunning && (
        <div className="eval-status-row">
          <span className="eval-status-line">
            {lastRelevantLog(job?.logs) ?? 'Starting…'}
          </span>
          <button
            type="button"
            className="eval-console-toggle"
            onClick={() => setConsoleOpen(o => !o)}
            title={consoleOpen ? 'Hide console' : 'Show console'}
          >
            {consoleOpen ? '▴' : '···'}
          </button>
        </div>
      )}
      {consoleOpen && (
        <div className="console-output">
          <pre ref={logViewerRef}>
            {job.logs?.length ? job.logs.join('\n') : 'Waiting for output…'}
          </pre>
        </div>
      )}

      <LiveViolationsFeed liveViolations={liveViolations} />

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
    </div>
  );
}
