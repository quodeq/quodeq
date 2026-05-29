import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import ScanProgress from './ScanProgress.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
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

function JobHeader({ job, projectLabel, onDismiss, onCancel }) {
  const isRunning = job.status === STATUS.RUNNING;
  const isDone = job.status === STATUS.DONE;
  return (
    <div className="evaluate-panel__top evaluate-panel__top--row">
      <TermHeader name={termNameForStatus(job.status)} sub={projectLabel || undefined} />
      <div className="evaluate-panel__top-actions">
        {isRunning && (
          <button type="button" className="term-btn term-btn--ghost term-btn--sm" onClick={onCancel}>cancel</button>
        )}
        {!isRunning && isDone && (
          <button type="button" className="term-btn term-btn--primary term-btn--sm" onClick={() => onDismiss('view')}>
            <span aria-hidden="true">▸</span> view results
          </button>
        )}
        {!isRunning && (
          <button type="button" className="term-btn term-btn--secondary term-btn--sm" onClick={() => onDismiss('close')}>close</button>
        )}
      </div>
    </div>
  );
}

function JobIdLine({ jobId, aiProvider, aiModel }) {
  return (
    <div className="evaluate-job-id-line">
      <span className="evaluate-job-id-line__label">job</span>
      <code>{jobId}</code>
      <CopyButton aria-label="Copy job ID" onClick={() => copyToClipboard(jobId)} />
      {aiProvider && aiModel && (
        <span data-testid="job-runtime-chip">
          {aiProvider}
          <span className="eval-provider-sep" aria-hidden="true"> · </span>
          {aiModel}
        </span>
      )}
    </div>
  );
}

export default function EvaluationStatus({ job, project, projectInfo, jobProjectInfo, liveViolations = {}, onDismiss, onCancel, hasEvaluations }) {
  if (!job) return null;
  // Prefer the running job's own project so the card stays accurate when the
  // UI's global selection points at a different project than the job is
  // actually scanning. Fall back to the selected project when the job's
  // project can't be resolved (e.g. before the report-path marker fires).
  const jobProjectLabel = jobProjectInfo?.displayName || jobProjectInfo?.name || null;
  const projectLabel = jobProjectLabel || projectInfo?.displayName || projectInfo?.name || project || null;

  return (
    <div className="panel evaluate-panel--terminal">
      <JobHeader job={job} projectLabel={projectLabel} onDismiss={onDismiss} onCancel={onCancel} />
      <JobStatStrip job={job} liveViolations={liveViolations} />
      <JobIdLine jobId={job.jobId} aiProvider={job.aiProvider} aiModel={job.aiModel} />
      <ScanProgress job={job} hasEvaluations={hasEvaluations} />
      <LiveViolationsFeed liveViolations={liveViolations} />
    </div>
  );
}
