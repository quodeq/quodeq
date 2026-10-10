/**
 * ScanProgress's smaller subcomponents/helpers: the failed/lost banner, the
 * coverage bar + legend, the summary line, and the footer.
 *
 * Presentational parts of ScanProgress.jsx — moved into named
 * functions/components so ScanProgress itself clears the
 * max-lines-per-function gate. Logic is unchanged from the pre-split
 * version.
 */
import ConsoleButton from '../../../components/ConsoleButton.jsx';
import ScanProgressDetail from './ScanProgressDetail.jsx';
import { computeCoverageView } from './scanProgressCoverage.js';
import { exitReasonInfo, exitReasonWarn, isTimeLimitExit } from '../../../models/exitReason.js';
import { t } from '../../../strings/index.js';
import { JOB_STATUS } from '../../../vocab/jobStatus.js';
import { PERCENT } from '../../../constants.js';

const STATUS_MARKERS = { arrow: '→', check: '✓', error: 'Error:', failed: 'failed' };
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

// Failed / lost: show the error message inline above the progress bar. When
// the run recorded a recognised exit reason (status.json, surfaced through
// the progress payload), lead with the human label and the actionable
// hint; keep the raw log line underneath as the detail.
export function ScanProgressBanner({ isFailed, isLost, status, progress, logs, exitReason }) {
  const reason = progress?.exitReason ?? exitReason;
  const failInfo = exitReasonInfo(reason);
  const failDetail = lastRelevantLog(logs);
  if (isFailed) {
    return (
      <div className="scan-progress__error" role="alert">
        {failInfo ? (
          <>
            <div><strong>{failInfo.label}</strong>{failInfo.hint && <> · {failInfo.hint}</>}</div>
            {failDetail && <div className="scan-progress__error-detail">{failDetail}</div>}
          </>
        ) : (failDetail || t('evaluate.analysisFailed'))}
      </div>
    );
  }
  if (isLost) {
    return <div className="scan-progress__error">{t('evaluate.jobTrackingLost')}</div>;
  }
  // Done but partial: the provider died mid-run, or the time budget ran out
  // with files left, after some files had been analysed. Warn that the
  // numbers below cover only part of the project.
  if (status === JOB_STATUS.DONE && failInfo && (exitReasonWarn(reason) || isTimeLimitExit(reason))) {
    return (
      <div className="scan-progress__warning" role="alert">
        <strong>{failInfo.label}</strong> · {t('evaluate.runStoppedEarly')}
        {failInfo.hint && <> · {failInfo.hint}</>}
      </div>
    );
  }
  return null;
}

// One bar for this run: files done out of the files it targets.
export function ScanProgressBar({ overallPct, isRunning }) {
  return (
    <div
      className="scan-progress__bar"
      role="progressbar"
      aria-label={t('evaluate.scanProgressAria')}
      aria-valuemin={0}
      aria-valuemax={PERCENT}
      aria-valuenow={Math.round(overallPct)}
    >
      <div
        className={`scan-progress__bar-fill${isRunning ? ' scan-progress__bar-fill--live' : ''}`}
        style={{ width: `${overallPct}%` }}
      />
    </div>
  );
}

// The bar's two actions, pills like the header's stop.
export function ScanProgressActions({ detailOpen, toggleDetail, consoleOpen, toggleConsole, jobId }) {
  return (
    <div className="scan-progress__actions">
      <button
        type="button"
        className="eval-pill-btn"
        onClick={toggleDetail}
        aria-expanded={detailOpen}
        aria-controls={`scan-progress-detail-${jobId}`}
        title={detailOpen ? t('evaluate.hideDetailTitle') : t('evaluate.showDetailTitle')}
      >
        {t('evaluate.details')}
        <span className={`scan-progress__caret${detailOpen ? ' scan-progress__caret--open' : ''}`} aria-hidden="true">▾</span>
      </button>
      <ConsoleButton className="eval-pill-btn" open={consoleOpen} onToggle={toggleConsole} />
    </div>
  );
}

// The full card body (everything ScanProgress renders once a jobId exists).
// Split out so ScanProgress itself only wires up hooks/state and delegates
// rendering here — logic unchanged from the pre-split version.
export function ScanProgressBody({ job, status, isRunning, isFailed, isLost, progress, detailOpen, toggleDetail, consoleOpen, toggleConsole, jobId }) {
  const { overallPct } = computeCoverageView(progress);
  return (
    <div className="scan-progress">
      <ScanProgressBanner isFailed={isFailed} isLost={isLost} status={status} progress={progress} logs={job.logs} exitReason={job.exitReason} />
      <div className="scan-progress__row">
        <ScanProgressBar overallPct={overallPct} isRunning={isRunning} />
        <ScanProgressActions
          detailOpen={detailOpen}
          toggleDetail={toggleDetail}
          consoleOpen={consoleOpen}
          toggleConsole={toggleConsole}
          jobId={jobId}
        />
      </div>
      {detailOpen && <ScanProgressDetail job={job} progress={progress} id={`scan-progress-detail-${jobId}`} />}
    </div>
  );
}
