import { useEffect, useState } from 'react';
import { useEvalLog } from '../eval-log/EvalLogContext.js';
import { pct, computeOverallProgress } from './scanProgressTotals.js';
import { deriveScanMode } from './buildJobStatCells.js';
import ConsoleButton from '../../../components/ConsoleButton.jsx';
import { SectionLabel } from '../../../components/terminal/index.js';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';
import { useRunElapsed } from '../hooks/useRunElapsed.js';
import { formatDuration, formatDurationCoarse } from '../../../utils/formatters.js';
import { exitReasonInfo, exitReasonLabel, exitReasonHint, exitReasonWarn } from '../../../models/exitReason.js';
import { t } from '../../../strings/index.js';

const TERMINAL_STATES = new Set(['done', 'failed', 'cancelled']);
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

// Reasons surfaced as a badge so an unusually large estimate isn't a mystery.
const ESTIMATE_REASON_LABEL = {
  'catching-up': t('evaluate.estimateCatchingUp'),
  'first-run': t('evaluate.estimateFirstRun'),
  'standards-changed': t('evaluate.estimateStandardsChanged'),
  'prompts-changed': t('evaluate.estimatePromptsChanged'),
};

function DimRow({ dim }) {
  const taken = dim.files?.taken ?? 0;
  const isPending = dim.state === 'pending';
  // Backend supplies accurate per-dim totals: a precomputed estimate for
  // pending dims, the live queue size for running/done. A 0 here means
  // estimates haven't landed yet — render nothing rather than a guess.
  const total = dim.files?.total ?? 0;
  const reasonLabel = ESTIMATE_REASON_LABEL[dim.estimateReason];
  const reasonBadge = reasonLabel
    ? <> · <span className="scan-progress__dim-reason">{reasonLabel}</span></>
    : null;
  // When the dimension reports `done`, force the bar to 100% even if
  // `files.taken < files.total` (incremental skips, dismissed files, etc.).
  // Backend `done` is the source of truth — count drift shouldn't make a
  // green dimension look red.
  const isDone = dim.state === 'done';
  const isRunning = dim.state === 'running';
  const p = isDone ? 100 : pct(taken, total);

  const dotClass = isDone ? ' scan-progress__dim-dot--done' : isRunning ? ' scan-progress__dim-dot--running' : '';

  let count;
  if (isPending) {
    count = total > 0
      ? <span className="scan-progress__dim-meta-projected">{t('evaluate.countOf', { taken: 0, total })}</span>
      : <span className="scan-progress__dim-meta-projected">{t('evaluate.estimating')}</span>;
  } else {
    count = <>{t('evaluate.countOf', { taken, total: total || '—' })}</>;
  }

  let meta;
  if (isPending) {
    meta = <span className="scan-progress__dim-meta-projected">{t('evaluate.queued')}{reasonBadge}</span>;
  } else if (isDone) {
    // Clamp adoption (sanctioned intended change): pct() caps at 100 where
    // the inline Math.round() above did not, so a done dim with taken>total
    // (count drift) no longer prints e.g. "105%". The null sentinel for a
    // zero total is preserved — it's load-bearing (chip renders only when
    // !== null).
    const coveragePct = total > 0 ? pct(taken, total) : null;
    const isPartial = typeof dim.exitReason === 'string' && dim.exitReason !== 'done';
    const hint = exitReasonHint(dim.exitReason);
    const partialTooltip = isPartial
      ? `${t('overview.stoppedReason', { reason: exitReasonLabel(dim.exitReason) })} · ${t('overview.filesOf', { read: taken, total })}${hint ? ` · ${hint}` : ''}`
      : undefined;
    meta = (
      <>
        {dim.violations > 0 && <><span className="scan-progress__v">{t('overview.violationsAbbrev', { count: dim.violations })}</span> · </>}
        {dim.compliance > 0 && <><span className="scan-progress__c">{t('evaluate.complianceAbbrev', { count: dim.compliance })}</span> · </>}
        {coveragePct !== null && (
          <><span
            className={`scan-progress__coverage${isPartial ? ' scan-progress__coverage--partial' : ''}`}
            title={partialTooltip}
          >{coveragePct}%</span>{dim.elapsedS != null && ' · '}</>
        )}
        {dim.elapsedS != null && formatDuration(dim.elapsedS)}
      </>
    );
  } else {
    // Only show a clock segment when we actually have a number to print.
    // Without this guard, a running dim with no elapsed time yields a
    // dangling "· —" tail. The time budget is run-level (shared across
    // dimensions, shown in the footer), so rows only get their elapsed.
    const clockPart = dim.elapsedS != null
      ? <span className="scan-progress__budget">{formatDuration(dim.elapsedS)}</span>
      : null;
    meta = (
      <>
        {dim.activeAgents > 0 && <>{t('evaluate.agents', { count: dim.activeAgents })}</>}
        {reasonBadge}
        {dim.violations > 0 && <> · <span className="scan-progress__v">{t('overview.violationsAbbrev', { count: dim.violations })}</span></>}
        {dim.compliance > 0 && <> · <span className="scan-progress__c">{t('evaluate.complianceAbbrev', { count: dim.compliance })}</span></>}
        {clockPart && <> · {clockPart}</>}
      </>
    );
  }

  const fillClass = isDone ? 'scan-progress__bar-fill--done' : '';

  return (
    <div className={`scan-progress__dim${isPending ? ' scan-progress__dim--pending' : ''}`}>
      <span className="scan-progress__dim-lead">
        <span className={`scan-progress__dim-dot${dotClass}`} aria-hidden="true" />
        <span className="scan-progress__dim-name">{dim.id}</span>
      </span>
      <span className="scan-progress__dim-count">{count}</span>
      <div className="scan-progress__bar scan-progress__bar--mini">
        <div className={`scan-progress__bar-fill ${fillClass}`} style={{ width: `${p}%` }} />
      </div>
      <span className="scan-progress__dim-meta">{meta}</span>
    </div>
  );
}


export default function ScanProgress({ job, hasEvaluations = false }) {
  const jobId = job?.jobId;
  const status = job?.status;
  const isRunning = status === 'running';
  const isFailed = status === 'failed';
  const isLost = status === 'lost';

  const [detailOpen, setDetailOpen] = useState(false);
  const evalLog = useEvalLog();
  const consoleOpen = evalLog.activeJobId === jobId;
  const isTerminal = TERMINAL_STATES.has(status);

  const progressQuery = useEvaluationProgress(jobId, isTerminal);
  // Best-effort: surface the last successful payload, ignore errors silently
  // (progress is purely informational and should never block the UI).
  const progress = progressQuery.data ?? null;
  // Same server-anchored ticking clock the stat strip shows, so the footer
  // total can never disagree with the ELAPSED tile.
  const elapsedS = useRunElapsed(job, progress, progressQuery.dataUpdatedAt);

  useEffect(() => {
    if (evalLog.activeJobId === jobId) {
      evalLog.updateJobStatus(status);
    }
  }, [evalLog, jobId, status]);

  if (!jobId) return null;

  const dims = progress?.dimensions || [];
  const { totalFiles, takenFiles, overallPct, projectTotal, cachedFiles, coveredFiles, coveredPct, excludedFiles } =
    computeOverallProgress(progress);
  // Segmented coverage view only when there is actually a cached portion to
  // show — full scans and legacy runs keep the familiar run-only display.
  const showCoverage = projectTotal > 0 && cachedFiles > 0;
  // coveredFiles is clamped to projectTotal upstream, so these widths can
  // never sum past 100 even when live queue counts drift from the estimate.
  // cachedPctWidth alone also can't exceed 100: the producer (_dim_estimates.py)
  // guarantees per-dim cached <= total, so summed cachedFiles <= projectTotal.
  const cachedPctWidth = showCoverage ? (cachedFiles / projectTotal) * 100 : 0;
  const runPctWidth = showCoverage ? ((coveredFiles - cachedFiles) / projectTotal) * 100 : 0;
  const scanMode = deriveScanMode(progress);
  const inlineLabel = progress?.currentDimension
    ? <>{t('evaluate.runningPrefix')} <span className="scan-progress__dim-active">{progress.currentDimension}</span></>
    : progress?.phase
      ? <>{t('evaluate.phasePrefix')} <span className="scan-progress__dim-active">{progress.phase}</span></>
      : null;

  function toggleDetail() {
    setDetailOpen((v) => !v);
  }
  function toggleConsole() {
    if (consoleOpen) {
      evalLog.closeLog();
    } else {
      evalLog.openLog(jobId, progress?.runId || null, status);
    }
  }

  // Failed / lost: show the error message inline above the progress bar.
  // When the run recorded a recognised exit reason (status.json, surfaced
  // through the progress payload), lead with the human label and the
  // actionable hint; keep the raw log line underneath as the detail.
  const failInfo = exitReasonInfo(progress?.exitReason);
  const failDetail = lastRelevantLog(job.logs);
  const errorBanner = isFailed
    ? (
      <div className="scan-progress__error">
        {failInfo ? (
          <>
            <div><strong>{failInfo.label}</strong>{failInfo.hint && <> · {failInfo.hint}</>}</div>
            {failDetail && <div className="scan-progress__error-detail">{failDetail}</div>}
          </>
        ) : (failDetail || t('evaluate.analysisFailed'))}
      </div>
    )
    : isLost
      ? <div className="scan-progress__error">{t('evaluate.jobTrackingLost')}</div>
      // Done-with-errors: the provider died mid-run but files had already
      // been analysed, so the run kept its partial results. Warn that the
      // numbers below cover only part of the project.
      : status === 'done' && failInfo && exitReasonWarn(progress?.exitReason)
        ? (
          <div className="scan-progress__warning">
            <strong>{failInfo.label}</strong> · {t('evaluate.runStoppedEarly')}
            {failInfo.hint && <> · {failInfo.hint}</>}
          </div>
        )
        : null;

  // The time limit is one deadline for the whole run, shared across all
  // selected dimensions — so the countdown pairs total elapsed with the
  // run-level budget. Overrun can show briefly: the watchdog allows a
  // short grace past the deadline before killing the job.
  const runBudgetS = progress?.budgetS;
  const overrun = runBudgetS > 0 && elapsedS > runBudgetS;
  const clockPart = isRunning && runBudgetS > 0
    ? (
      <> · <span className={overrun ? 'scan-progress__budget scan-progress__budget--overrun' : 'scan-progress__budget'}>
        {t('evaluate.elapsedOfBudget', { elapsed: formatDuration(elapsedS), budget: formatDurationCoarse(runBudgetS) })}
      </span></>
    )
    : elapsedS != null
      ? <> · {t('evaluate.elapsedTotal', { elapsed: formatDuration(elapsedS) })}</>
      : null;

  let summary;
  if (showCoverage) {
    summary = totalFiles > 0
      ? <>{t('evaluate.targetsPrefix')} <strong>{totalFiles}</strong> {t('evaluate.changedFilesSuffix')} · {t('evaluate.doneCount', { count: takenFiles, pct: overallPct })}{excludedFiles > 0 && <> · {t('evaluate.excludedSizeCap', { count: excludedFiles })}</>}{clockPart}</>
      : <>{t('evaluate.nothingNew')}{clockPart}</>;
  } else if (totalFiles > 0) {
    summary = scanMode === 'clean'
      ? <>{t('evaluate.reanalyzesPrefix')} <strong>{totalFiles}</strong> {t('evaluate.filesLabel')} · {t('evaluate.doneCount', { count: takenFiles, pct: overallPct })}{excludedFiles > 0 && <> · {t('evaluate.excludedSizeCap', { count: excludedFiles })}</>}{clockPart}</>
      : <><strong>{t('evaluate.countOf', { taken: takenFiles, total: totalFiles })}</strong> {t('evaluate.checksLabel')} · {overallPct}%{isRunning && inlineLabel && <> · {inlineLabel}</>}{clockPart}</>;
  } else {
    summary = <><strong>{t('evaluate.preparing')}</strong>{isRunning && inlineLabel && <> · {inlineLabel}</>}</>;
  }

  return (
    <div className="scan-progress">
      <div className="scan-progress__head">
        <SectionLabel>
          {showCoverage ? t('evaluate.repoCoverageFiles', { count: projectTotal }) : t('evaluate.progressLabel')}
        </SectionLabel>
        {showCoverage && <span className="scan-progress__head-pct">{t('evaluate.pctAnalyzed', { pct: coveredPct })}</span>}
      </div>
      {errorBanner}
      <div
        className="scan-progress__bar"
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
      {detailOpen && dims.length > 0 && (
        <div className="scan-progress__expanded" id={`scan-progress-detail-${jobId}`}>
          <div className="scan-progress__expanded-label">{t('evaluate.perDimension')}</div>
          {dims.map((d) => <DimRow key={d.id} dim={d} />)}
        </div>
      )}
    </div>
  );
}
