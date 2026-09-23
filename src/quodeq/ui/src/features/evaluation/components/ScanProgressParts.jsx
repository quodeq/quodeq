/**
 * ScanProgress's smaller subcomponents/helpers: the failed/lost banner, the
 * coverage bar + legend, the summary line, and the footer.
 *
 * Split out of ScanProgress.jsx verbatim — moved into named
 * functions/components so ScanProgress itself clears the
 * max-lines-per-function gate. Logic is unchanged from the pre-split
 * version.
 */
import ConsoleButton from '../../../components/ConsoleButton.jsx';
import DimRow from './DimRow.jsx';
import { computeCoverageView, computeRunBudget } from './scanProgressCoverage.js';
import { deriveScanMode } from './buildJobStatCells.js';
import { SCAN_MODE } from './scanModes.js';
import { SectionLabel } from '../../../components/terminal/index.js';
import { formatDuration, formatDurationCoarse } from '../../../utils/formatters.js';
import { exitReasonInfo, exitReasonWarn } from '../../../models/exitReason.js';
import { t } from '../../../strings/index.js';
import { JOB_STATUS } from '../../../vocab/jobStatus.js';

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
  // Done-with-errors: the provider died mid-run but files had already been
  // analysed, so the run kept its partial results. Warn that the numbers
  // below cover only part of the project.
  if (status === JOB_STATUS.DONE && failInfo && exitReasonWarn(reason)) {
    return (
      <div className="scan-progress__warning" role="alert">
        <strong>{failInfo.label}</strong> · {t('evaluate.runStoppedEarly')}
        {failInfo.hint && <> · {failInfo.hint}</>}
      </div>
    );
  }
  return null;
}

export function ScanProgressBar({ showCoverage, cachedFiles, cachedPctWidth, runPctWidth, overallPct, coveredPct, isRunning, projectTotal, coveredFiles, takenFiles }) {
  return (
    <>
      <div
        className="scan-progress__bar"
        role="progressbar"
        aria-label={t('evaluate.scanProgressAria')}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(showCoverage ? coveredPct : overallPct)}
        title={showCoverage ? t('evaluate.cachedBarTitle', { count: cachedFiles }) : undefined}
      >
        {showCoverage && (
          <div
            className="scan-progress__bar-fill scan-progress__bar-fill--cached"
            style={{ width: `${cachedPctWidth}%` }}
          />
        )}
        <div
          className={`scan-progress__bar-fill${isRunning ? ' scan-progress__bar-fill--live' : ''}`}
          style={{ width: showCoverage ? `${runPctWidth}%` : `${overallPct}%` }}
        />
      </div>
      {showCoverage && (
        <div className="scan-progress__legend">
          <span className="scan-progress__legend-item">
            <span className="scan-progress__legend-swatch scan-progress__legend-swatch--cached" aria-hidden="true" />
            {t('evaluate.legendCached', { count: cachedFiles })}
          </span>
          <span className="scan-progress__legend-item">
            <span className="scan-progress__legend-swatch scan-progress__legend-swatch--run" aria-hidden="true" />
            {t('evaluate.legendRun', { count: takenFiles })}
          </span>
          <span className="scan-progress__legend-item">
            <span className="scan-progress__legend-swatch scan-progress__legend-swatch--track" aria-hidden="true" />
            {t('evaluate.legendRemaining', { count: Math.max(0, projectTotal - coveredFiles) })}
          </span>
        </div>
      )}
    </>
  );
}

export function ScanProgressFoot({ summary, detailOpen, toggleDetail, consoleOpen, toggleConsole, jobId }) {
  return (
    <div className="scan-progress__foot">
      <span className="scan-progress__foot-summary">{summary}</span>
      <div className="scan-progress__actions">
        <button
          type="button"
          className={`scan-progress__detail-toggle${detailOpen ? ' scan-progress__detail-toggle--open' : ''}`}
          onClick={toggleDetail}
          aria-expanded={detailOpen}
          aria-controls={`scan-progress-detail-${jobId}`}
          title={detailOpen ? t('evaluate.hideDetailTitle') : t('evaluate.showDetailTitle')}
        >
          <span className="scan-progress__detail-label">
            {/* Ghost label reserves the width of the longest label so the
                button (and therefore the layout to its left) doesn't
                reflow when toggling between "show detail" and "hide detail". */}
            <span className="scan-progress__detail-label-ghost" aria-hidden="true">{t('evaluate.showDetail')}</span>
            <span className="scan-progress__detail-label-active">{detailOpen ? t('evaluate.hideDetail') : t('evaluate.showDetail')}</span>
          </span>
          <span className={`scan-progress__caret${detailOpen ? ' scan-progress__caret--open' : ''}`} aria-hidden="true">▸</span>
        </button>
        <ConsoleButton open={consoleOpen} onToggle={toggleConsole} />
      </div>
    </div>
  );
}

function buildInlineLabel(progress) {
  if (progress?.currentDimension) {
    return <>{t('evaluate.runningPrefix')} <span className="scan-progress__dim-active">{progress.currentDimension}</span></>;
  }
  if (progress?.phase) {
    return <>{t('evaluate.phasePrefix')} <span className="scan-progress__dim-active">{progress.phase}</span></>;
  }
  return null;
}

// The time limit is one deadline for the whole run, shared across all
// selected dimensions — so the countdown pairs total elapsed with the
// run-level budget. Overrun can show briefly: the watchdog allows a short
// grace past the deadline before killing the job.
function buildClockPart({ isRunning, runBudgetS, overrun, elapsedS }) {
  if (isRunning && runBudgetS > 0) {
    return (
      <> · <span className={overrun ? 'scan-progress__budget scan-progress__budget--overrun' : 'scan-progress__budget'}>
        {t('evaluate.elapsedOfBudget', { elapsed: formatDuration(elapsedS), budget: formatDurationCoarse(runBudgetS) })}
      </span></>
    );
  }
  if (elapsedS != null) {
    return <> · {t('evaluate.elapsedTotal', { elapsed: formatDuration(elapsedS) })}</>;
  }
  return null;
}

// The "N done · X excluded · clock" tail both file-count summaries end with.
// Kept on one line: a line break inside JSX text changes the rendered
// whitespace.
function buildDoneTail({ takenFiles, overallPct, excludedFiles, clockPart }) {
  return <>{t('evaluate.doneCount', { count: takenFiles, pct: overallPct })}{excludedFiles > 0 && <> · {t('evaluate.excludedSizeCap', { count: excludedFiles })}</>}{clockPart}</>;
}

// The four shapes buildSummary picks between. Each stays on one line because
// a line break inside JSX text changes the rendered whitespace.
function coverageLine({ totalFiles, tail }) {
  return <>{t('evaluate.targetsPrefix')} <strong>{totalFiles}</strong> {t('evaluate.changedFilesSuffix')} · {tail}</>;
}

function cleanScanLine({ totalFiles, tail }) {
  return <>{t('evaluate.reanalyzesPrefix')} <strong>{totalFiles}</strong> {t('evaluate.filesLabel')} · {tail}</>;
}

function incrementalLine({ takenFiles, totalFiles, overallPct, isRunning, inlineLabel, clockPart }) {
  return <><strong>{t('evaluate.countOf', { taken: takenFiles, total: totalFiles })}</strong> {t('evaluate.checksLabel')} · {overallPct}%{isRunning && inlineLabel && <> · {inlineLabel}</>}{clockPart}</>;
}

function preparingLine({ isRunning, inlineLabel }) {
  return <><strong>{t('evaluate.preparing')}</strong>{isRunning && inlineLabel && <> · {inlineLabel}</>}</>;
}

export function buildSummary({ showCoverage, totalFiles, takenFiles, overallPct, excludedFiles, scanMode, isRunning, progress, elapsedS, runBudgetS, overrun }) {
  const inlineLabel = buildInlineLabel(progress);
  const clockPart = buildClockPart({ isRunning, runBudgetS, overrun, elapsedS });
  const tail = () => buildDoneTail({ takenFiles, overallPct, excludedFiles, clockPart });

  // `> 0`, not `!== 0`: an absent or non-finite count reads as "nothing to
  // report yet" too, and would otherwise fall through to a line that renders
  // it verbatim.
  const hasFiles = totalFiles > 0;

  if (showCoverage && !hasFiles) return <>{t('evaluate.nothingNew')}{clockPart}</>;
  if (showCoverage) return coverageLine({ totalFiles, tail: tail() });
  if (!hasFiles) return preparingLine({ isRunning, inlineLabel });
  if (scanMode === SCAN_MODE.CLEAN) return cleanScanLine({ totalFiles, tail: tail() });
  return incrementalLine({ takenFiles, totalFiles, overallPct, isRunning, inlineLabel, clockPart });
}

// The full card body (everything ScanProgress renders once a jobId exists).
// Split out so ScanProgress itself only wires up hooks/state and delegates
// rendering here — logic unchanged from the pre-split version.
export function ScanProgressBody({ job, status, isRunning, isFailed, isLost, progress, elapsedS, detailOpen, toggleDetail, consoleOpen, toggleConsole, jobId }) {
  const dims = progress?.dimensions || [];
  const {
    totalFiles, takenFiles, overallPct, projectTotal, cachedFiles, coveredFiles, coveredPct, excludedFiles,
    showCoverage, cachedPctWidth, runPctWidth,
  } = computeCoverageView(progress);
  const scanMode = deriveScanMode(progress);
  const { runBudgetS, overrun } = computeRunBudget(progress, elapsedS);
  const summary = buildSummary({
    showCoverage, totalFiles, takenFiles, overallPct, excludedFiles, scanMode, isRunning,
    progress, elapsedS, runBudgetS, overrun,
  });

  return (
    <div className="scan-progress">
      <div className="scan-progress__head">
        <SectionLabel>
          {showCoverage ? t('evaluate.repoCoverageFiles', { count: projectTotal }) : t('evaluate.progressLabel')}
        </SectionLabel>
        {showCoverage && <span className="scan-progress__head-pct">{t('evaluate.pctAnalyzed', { pct: coveredPct })}</span>}
      </div>
      <ScanProgressBanner isFailed={isFailed} isLost={isLost} status={status} progress={progress} logs={job.logs} exitReason={job.exitReason} />
      <ScanProgressBar
        showCoverage={showCoverage}
        cachedFiles={cachedFiles}
        cachedPctWidth={cachedPctWidth}
        runPctWidth={runPctWidth}
        overallPct={overallPct}
        coveredPct={coveredPct}
        isRunning={isRunning}
        projectTotal={projectTotal}
        coveredFiles={coveredFiles}
        takenFiles={takenFiles}
      />
      <ScanProgressFoot
        summary={summary}
        detailOpen={detailOpen}
        toggleDetail={toggleDetail}
        consoleOpen={consoleOpen}
        toggleConsole={toggleConsole}
        jobId={jobId}
      />
      {detailOpen && dims.length > 0 && (
        <div className="scan-progress__expanded" id={`scan-progress-detail-${jobId}`}>
          <div className="scan-progress__expanded-label">{t('evaluate.perDimension')}</div>
          {dims.map((d) => <DimRow key={d.id} dim={d} />)}
        </div>
      )}
    </div>
  );
}
