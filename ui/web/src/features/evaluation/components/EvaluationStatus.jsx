import { useEffect, useRef } from 'react';

export default function EvaluationStatus({ job, onDismiss }) {
  const logViewerRef = useRef(null);

  useEffect(() => {
    if (logViewerRef.current) {
      logViewerRef.current.scrollTop = logViewerRef.current.scrollHeight;
    }
  }, [job?.logs]);

  if (!job) return null;

  const isRunning = job.status === 'running';
  const isDone = job.status === 'completed';

  return (
    <div className="panel evaluate-job-panel">
      <div className="job-header">
        <h3>Evaluation Progress</h3>
        <span className={`job-status-badge ${job.status}`}>{job.status}</span>
      </div>

      <div className="job-info">
        <div className="job-info-item">
          <span className="job-info-label">Job ID</span>
          <code>{job.jobId}</code>
        </div>
        {job.repo && (
          <div className="job-info-item">
            <span className="job-info-label">Repository</span>
            <code>{job.repo}</code>
          </div>
        )}
      </div>

      <div className="console-output">
        <pre ref={logViewerRef}>
          {job.logs?.length ? job.logs.join('\n') : 'Waiting for output...'}
        </pre>
      </div>

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
