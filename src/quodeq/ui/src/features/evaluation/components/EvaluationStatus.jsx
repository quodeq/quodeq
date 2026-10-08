import { useMemo } from 'react';
import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import ScanProgress from './ScanProgress.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import JobStatStrip from './JobStatStrip.jsx';
import { IdentityStrip, IdentityCell } from './IdentityStrip.jsx';
import { deriveScanMode } from './buildJobStatCells.js';
import { SCAN_MODE } from './scanModes.js';
import { isExternal, isDiffReview, diffFileCount, externalLabel, githubLink, SHORT_SHA } from '../externalRun.js';
import { openExternal } from '../../updates/openExternal.js';
import { formatRunTime } from '../../../utils/dateFormatting.js';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';
import useLiveFeedSettings from '../../settings/hooks/useLiveFeedSettings.js';
import { exitReasonLabel, isTimeLimitExit } from '../../../models/exitReason.js';
import { t } from '../../../strings/index.js';
import { jobStatusLabel } from '../../../strings/labels.js';
import { JOB_STATUS, JOB_TERMINAL } from '../../../vocab/jobStatus.js';
import { EVAL_DISMISS_ACTION } from '../evaluationVocab.js';

// A cancelled/failed job whose run hit its time budget is not an error:
// the header must agree with the coverage banner below it, which already
// says "time limit reached" from the run's status.json. Done runs keep
// their "complete" header; the banner tells the truncation story there.
function isTimeLimitEnd(status, exitReason) {
  return (status === JOB_STATUS.CANCELLED || status === JOB_STATUS.FAILED) && isTimeLimitExit(exitReason);
}

function termNameForStatus(status, exitReason) {
  if (status === JOB_STATUS.RUNNING) return t('evaluate.termInProgress');
  if (isTimeLimitEnd(status, exitReason)) return t('evaluate.termTimeLimit');
  if (status === JOB_STATUS.DONE)    return t('evaluate.termComplete');
  if (status === JOB_STATUS.FAILED)  return t('evaluate.termFailed');
  if (status === JOB_STATUS.LOST)    return t('evaluate.termLost');
  return t('evaluate.termCancelled');
}

// A running job shows a pulsing dot: the title already says the run is in
// progress. Finished jobs keep a pill that names how they ended.
function RunPill({ status, exitReason }) {
  if (status === JOB_STATUS.RUNNING) {
    return <span className="eval-run-dot" role="img" aria-label={t('evaluate.runningAria')} />;
  }
  // Finished: the dot settles into a still check. Other endings keep a pill
  // that names how the run ended, which the title alone does not say.
  if (status === JOB_STATUS.DONE) {
    return <span className="eval-run-check" role="img" aria-label={t('evaluate.completeAria')}>✓</span>;
  }
  const timeLimit = isTimeLimitEnd(status, exitReason);
  const mod = status === JOB_STATUS.DONE ? 'done'
    : !timeLimit && (status === JOB_STATUS.FAILED || status === JOB_STATUS.LOST) ? 'failed'
    : 'neutral';
  return (
    <span className={`eval-run-pill eval-run-pill--${mod}`}>
      {timeLimit ? exitReasonLabel(exitReason) : jobStatusLabel(status)}
    </span>
  );
}

// A run this app did not start says where it came from after its status
// mark ("nightly", "PR review #1402"), or "external" when it recorded no
// origin; a run over a diff without a PR number says "diff review" too.
function ExternalTag({ job, progress }) {
  if (!isExternal(job)) return null;
  const label = externalLabel(job);
  const diff = isDiffReview(progress) && !Number.isInteger(job.origin?.pr);
  return <span className="eval-run-tag">{diff ? `${label} · ${t('evaluate.diffReviewTag')}` : label}</span>;
}

// A PR review that has ended: its results are the review comment on the
// pull request, not a run in this app.
function isReviewEnd(job, progress) {
  return job.status !== JOB_STATUS.RUNNING && isExternal(job) && isDiffReview(progress);
}

// Where an ended PR review's results are. Only a review that finished says
// it was posted; one whose folder vanished may never have reached the post
// step, and one that was stopped or failed did not.
function ReviewEndLine({ job, progress }) {
  if (!isReviewEnd(job, progress) || job.status !== JOB_STATUS.DONE) return null;
  return <p className="eval-review-posted">{t(job.vanished ? 'evaluate.reviewGoesToPr' : 'evaluate.reviewPosted')}</p>;
}

function StatusMark({ job }) {
  // A run whose folder vanished ended in a way nobody recorded here: a
  // neutral "ended", never a guessed "complete" or the red "lost".
  if (job.vanished) return <span className="eval-run-pill eval-run-pill--neutral">{t('evaluate.endedPill')}</span>;
  return <RunPill status={job.status} exitReason={job.exitReason} />;
}

function PrimaryPill({ label, onClick }) {
  return (
    <button type="button" className="eval-scan-pill eval-scan-pill--sm" onClick={onClick}>
      <span className="eval-scan-pill__glyph" aria-hidden="true">▶</span>
      {label}
    </button>
  );
}

function JobActions({ job, progress, onDismiss, onCancel }) {
  if (job.status === JOB_STATUS.RUNNING) {
    return (
      <button type="button" className="eval-pill-btn eval-pill-btn--stop" onClick={onCancel}>
        <span className="eval-pill-btn__stop-glyph" aria-hidden="true" />
        {t('evaluate.stopBtn')}
      </button>
    );
  }
  const reviewEnd = isReviewEnd(job, progress);
  const commitUrl = reviewEnd ? githubLink(job) : null;
  return (
    <>
      {commitUrl && <PrimaryPill label={t('evaluate.openOnGitHub')} onClick={() => openExternal(commitUrl)} />}
      {!reviewEnd && !job.vanished && job.status === JOB_STATUS.DONE && (
        <PrimaryPill label={t('evaluate.viewResults')} onClick={() => onDismiss(EVAL_DISMISS_ACTION.VIEW)} />
      )}
      <button type="button" className="eval-pill-btn" onClick={() => onDismiss(EVAL_DISMISS_ACTION.CLOSE)}>{t('evaluate.closeBtn')}</button>
    </>
  );
}

function JobHeader({ job, progress, onDismiss, onCancel }) {
  const name = job.vanished ? t('evaluate.termEnded') : termNameForStatus(job.status, job.exitReason);
  return (
    <div className="evaluate-panel__top evaluate-panel__top--row">
      <TermHeader name={name} badge={<><StatusMark job={job} /><ExternalTag job={job} progress={progress} /></>} />
      <div className="evaluate-panel__top-actions">
        <JobActions job={job} progress={progress} onDismiss={onDismiss} onCancel={onCancel} />
      </div>
    </div>
  );
}

function modeLabel(progress) {
  const mode = deriveScanMode(progress);
  if (mode === SCAN_MODE.DIFF) return t('evaluate.modeDiff', { count: diffFileCount(progress) });
  return mode ?? '—';
}

// When an external run started, and on which commit: the app did not start
// it, so the strip says what it is looking at.
function StartedCell({ job }) {
  if (!isExternal(job) || !job.startedAt) return null;
  return (
    <IdentityCell label={t('evaluate.idStarted')}>
      {formatRunTime(job.startedAt, '—', 'JobIdentityStrip')}
      {job.commitSha && (
        <>
          <span className="eval-provider-sep" aria-hidden="true"> · </span>
          {job.commitSha.slice(0, SHORT_SHA)}
        </>
      )}
    </IdentityCell>
  );
}

function JobIdentityStrip({ job, progress, projectLabel, onGoToProjects }) {
  return (
    <IdentityStrip>
      {/* "Unknown beats wrong": a dash, never the global selection. */}
      {/* The job id lives in the progress details; the repository opens
          Repositories, like the setup card's repository cell. */}
      <IdentityCell
        label={t('evaluate.idRepository')}
        grow
        title={projectLabel ? t('evaluate.openProjectsTitle') : undefined}
        onClick={projectLabel ? onGoToProjects : undefined}
      >
        {projectLabel ?? '—'}
      </IdentityCell>
      <StartedCell job={job} />
      {job.aiProvider && job.aiModel && (
        <IdentityCell label={t('evaluate.idModel')}>
          <span data-testid="job-runtime-chip">
            {job.aiProvider}
            <span className="eval-provider-sep" aria-hidden="true"> · </span>
            {job.aiModel}
          </span>
        </IdentityCell>
      )}
      <IdentityCell label={t('evaluate.idMode')}>{modeLabel(progress)}</IdentityCell>
    </IdentityStrip>
  );
}

function labelOf(project) {
  return project?.displayName || project?.name || null;
}

function countAll(byDim) {
  return Object.values(byDim).reduce((n, vs) => n + vs.length, 0);
}

export default function EvaluationStatus({ job, jobProjectInfo, startedProjectInfo, liveViolations = {}, onDismiss, onCancel, onGoToProjects }) {
  const { newOnly } = useLiveFeedSettings();
  // Shares the strip/progress query cache entry: no extra polling.
  const { data: progress } = useEvaluationProgress(job?.jobId, !job || JOB_TERMINAL.has(job.status));
  // Filter ONCE, above both consumers. JobStatStrip derives its violations
  // cell from the same object the feed lists, so filtering in each child
  // separately is how the counter and the list drift apart (see #878).
  const { shown, fresh, hiddenCarriedCount } = useMemo(() => {
    // `fresh` is this run's findings only: the tile and the feed head count
    // it whatever the setting shows. `shown` is what the rows list.
    const freshOnly = {};
    let carried = 0;
    for (const [dim, vs] of Object.entries(liveViolations || {})) {
      // Both cache writers normalise through createViolation now, so entries
      // carry `carriedForward`. The snake_case spelling stays accepted: the
      // SSE stream used to write raw wire payloads
      // here, and an entry written before this must not read as fresh.
      const keep = (vs || []).filter((v) => !(v.carriedForward ?? v.carried_forward));
      carried += (vs || []).length - keep.length;
      if (keep.length) freshOnly[dim] = keep;
    }
    return newOnly
      ? { shown: freshOnly, fresh: freshOnly, hiddenCarriedCount: carried }
      : { shown: liveViolations, fresh: freshOnly, hiddenCarriedCount: 0 };
  }, [liveViolations, newOnly]);

  if (!job) return null;
  // Prefer the running job's own project so the card stays accurate when the
  // UI's global selection points at a different project than the job is
  // actually scanning. Before the report-path marker resolves it, fall back
  // to the project the job was STARTED for. Never fall back to the global
  // selection: switching projects mid-run would mislabel a running
  // evaluation with a project it never touched. Unknown beats wrong.
  const projectLabel = labelOf(jobProjectInfo) || labelOf(startedProjectInfo) || null;

  return (
    <div className="panel evaluate-panel--terminal">
      <JobHeader job={job} progress={progress} onDismiss={onDismiss} onCancel={onCancel} />
      <JobIdentityStrip job={job} progress={progress} projectLabel={projectLabel} onGoToProjects={onGoToProjects} />
      <ReviewEndLine job={job} progress={progress} />
      <JobStatStrip job={job} liveViolations={fresh} hiddenCarriedCount={hiddenCarriedCount} />
      <ScanProgress job={job} />
      <LiveViolationsFeed job={job} liveViolations={shown} newCount={countAll(fresh)} hiddenCarriedCount={hiddenCarriedCount} />
    </div>
  );
}
