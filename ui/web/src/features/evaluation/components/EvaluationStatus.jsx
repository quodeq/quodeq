import { useEffect, useRef, useState } from 'react';

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

export default function EvaluationStatus({ job, onDismiss, onCancel }) {
  const logViewerRef = useRef(null);
  const [consoleOpen, setConsoleOpen] = useState(false);

  function lastRelevantLog(logs) {
    if (!logs?.length) return null;
    for (let i = logs.length - 1; i >= 0; i--) {
      const line = logs[i].trim();
      if (line.length >= 15) return line;
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
          {isRunning && <span className="job-spinner" />}
          <h3>{statusTitle(job.status)}</h3>
        </div>
        <span className={`job-status-badge ${job.status}`}>{job.status}</span>
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
          <code className="job-meta-code job-meta-code--muted">{job.jobId}</code>
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

      <div className="job-actions">
        {isRunning ? (
          <button className="job-cancel-btn" onClick={onCancel}>
            Cancel
          </button>
        ) : (
          <>
            {isDone && (
              <button className="view-results-btn" onClick={() => onDismiss('view')}>
                View Results
              </button>
            )}
            <button className="job-close-btn" onClick={() => onDismiss('close')}>
              {isDone ? 'Dismiss' : 'Close'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
