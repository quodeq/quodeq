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
  'catching-up': 'catching up',
  'first-run': 'first run',
  'standards-changed': 'standards changed',
  'prompts-changed': 'prompts changed',
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
      ? <span className="scan-progress__dim-meta-projected">0 / {total}</span>
      : <span className="scan-progress__dim-meta-projected">estimating…</span>;
  } else {
    count = <>{taken} / {total || '—'}</>;
  }

  let meta;
  if (isPending) {
    meta = <span className="scan-progress__dim-meta-projected">queued{reasonBadge}</span>;
  } else if (isDone) {
    const coveragePct = total > 0 ? Math.round((taken / total) * 100) : null;
    const isPartial = typeof dim.exitReason === 'string' && dim.exitReason !== 'done';
    const hint = exitReasonHint(dim.exitReason);
    const partialTooltip = isPartial
      ? `stopped: ${exitReasonLabel(dim.exitReason)} · ${taken} of ${total} files${hint ? ` · ${hint}` : ''}`
      : undefined;
    meta = (
      <>
        {dim.violations > 0 && <><span className="scan-progress__v">{dim.violations}v</span> · </>}
        {dim.compliance > 0 && <><span className="scan-progress__c">{dim.compliance}c</span> · </>}
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
        {dim.activeAgents > 0 && <>{dim.activeAgents} agents</>}
        {reasonBadge}
        {dim.violations > 0 && <> · <span className="scan-progress__v">{dim.violations}v</span></>}
        {dim.compliance > 0 && <> · <span className="scan-progress__c">{dim.compliance}c</span></>}
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
    ? <>running <span className="scan-progress__dim-active">{progress.currentDimension}</span></>
    : progress?.phase
      ? <>phase: <span className="scan-progress__dim-active">{progress.phase}</span></>
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
        ) : (failDetail || 'Analysis failed')}
      </div>
    )
    : isLost
      ? <div className="scan-progress__error">Server restarted, job tracking lost</div>
      // Done-with-errors: the provider died mid-run but files had already
      // been analysed, so the run kept its partial results. Warn that the
      // numbers below cover only part of the project.
      : status === 'done' && failInfo && exitReasonWarn(progress?.exitReason)
        ? (
          <div className="scan-progress__warning">
            <strong>{failInfo.label}</strong> · run stopped early, results are partial
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
        {formatDuration(elapsedS)} of {formatDurationCoarse(runBudgetS)} budget
      </span></>
    )
    : elapsedS != null
      ? <> · {formatDuration(elapsedS)} total</>
      : null;

  let summary;
  if (showCoverage) {
    summary = totalFiles > 0
      ? <>this run targets <strong>{totalFiles}</strong> changed files · {takenFiles} done ({overallPct}%){excludedFiles > 0 && <> · {excludedFiles} excluded (size cap)</>}{clockPart}</>
      : <>nothing new this run{clockPart}</>;
  } else if (totalFiles > 0) {
    summary = scanMode === 'clean scan'
      ? <>this run re-analyzes all <strong>{totalFiles}</strong> files · {takenFiles} done ({overallPct}%){excludedFiles > 0 && <> · {excludedFiles} excluded (size cap)</>}{clockPart}</>
      : <><strong>{takenFiles} / {totalFiles}</strong> checks · {overallPct}%{isRunning && inlineLabel && <> · {inlineLabel}</>}{clockPart}</>;
  } else {
    summary = <><strong>preparing…</strong>{isRunning && inlineLabel && <> · {inlineLabel}</>}</>;
  }

  return (
    <div className="scan-progress">
      <div className="scan-progress__head">
        <SectionLabel>
          {showCoverage ? <>repository coverage · {projectTotal} files</> : 'progress'}
        </SectionLabel>
        {showCoverage && <span className="scan-progress__head-pct">{coveredPct}% analyzed</span>}
      </div>
      {errorBanner}
      <div
        className="scan-progress__bar"
        title={showCoverage ? `${cachedFiles} files analyzed in previous runs` : undefined}
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
            {cachedFiles} cached from earlier runs
          </span>
          <span className="scan-progress__legend-item">
            <span className="scan-progress__legend-swatch scan-progress__legend-swatch--run" aria-hidden="true" />
            {takenFiles} analyzed in this run
          </span>
          <span className="scan-progress__legend-item">
            <span className="scan-progress__legend-swatch scan-progress__legend-swatch--track" aria-hidden="true" />
            {Math.max(0, projectTotal - coveredFiles)} not yet analyzed
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
            title={detailOpen ? 'Hide per-dimension detail' : 'Show per-dimension detail'}
          >
            <span className="scan-progress__detail-label">
              {/* Ghost label reserves the width of the longest label so the
                  button (and therefore the layout to its left) doesn't
                  reflow when toggling between "show detail" and "hide detail". */}
              <span className="scan-progress__detail-label-ghost" aria-hidden="true">show detail</span>
              <span className="scan-progress__detail-label-active">{detailOpen ? 'hide detail' : 'show detail'}</span>
            </span>
            <span className={`scan-progress__caret${detailOpen ? ' scan-progress__caret--open' : ''}`} aria-hidden="true">▸</span>
          </button>
          <ConsoleButton open={consoleOpen} onToggle={toggleConsole} />
        </div>
      </div>
      {detailOpen && dims.length > 0 && (
        <div className="scan-progress__expanded" id={`scan-progress-detail-${jobId}`}>
          <div className="scan-progress__expanded-label">per dimension</div>
          {dims.map((d) => <DimRow key={d.id} dim={d} />)}
        </div>
      )}
    </div>
  );
}
