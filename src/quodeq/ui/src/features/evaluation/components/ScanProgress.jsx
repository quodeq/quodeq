import { useEffect, useRef, useState } from 'react';
import { getEvaluationProgress } from '../../../api/index.js';
import ConsoleLogViewer from './ConsoleLogViewer.jsx';
import { CONSOLE_DOT_DISMISSED_KEY } from '../../../constants.js';

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATES = new Set(['done', 'failed', 'cancelled']);
const STATUS_MARKERS = { arrow: '\u2192', check: '\u2713', error: 'Error:', failed: 'failed' };

function formatClock(s) {
  if (s == null || !Number.isFinite(s)) return '—';
  const total = Math.max(0, Math.floor(s));
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

function pct(taken, total) {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((taken / total) * 100));
}

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

function DimRow({ dim, fallbackTotal }) {
  const taken = dim.files?.taken ?? 0;
  const isPending = dim.state === 'pending';
  // Pending dims don't have a real queue yet. Use the running/done dims'
  // queue total as a better estimate than the project-wide upper bound.
  const total = isPending && fallbackTotal ? fallbackTotal : (dim.files?.total ?? 0);
  // When the dimension reports `done`, force the bar to 100% even if
  // `files.taken < files.total` (incremental skips, dismissed files, etc.).
  // Backend `done` is the source of truth — count drift shouldn't make a
  // green dimension look red.
  const isDone = dim.state === 'done';
  const isRunning = dim.state === 'running';
  const p = isDone ? 100 : pct(taken, total);

  let icon = '○';
  let iconClass = '';
  if (isDone) {
    icon = '✓';
    iconClass = 'scan-progress__dim-icon--done';
  } else if (isRunning) {
    icon = '▶';
    iconClass = 'scan-progress__dim-icon--running';
  }

  let meta;
  if (isPending) {
    meta = total > 0
      ? <span className="scan-progress__dim-meta-projected">0 / {total}</span>
      : null;
  } else if (isDone) {
    meta = (
      <>
        {total > 0 ? `${taken} files` : ''}
        {dim.violations > 0 && <> · <span className="scan-progress__v">{dim.violations}v</span></>}
        {dim.compliance > 0 && <> · <span className="scan-progress__c">{dim.compliance}c</span></>}
        {dim.elapsedS != null && <> · {formatClock(dim.elapsedS)}</>}
      </>
    );
  } else {
    // Only show a clock segment when we actually have a number to print.
    // Without this guard, a running dim with no elapsed time yields a
    // dangling "· —" tail.
    let budgetPart = null;
    if (dim.budgetS) {
      const overrun = dim.elapsedS != null && dim.elapsedS > dim.budgetS;
      const cls = overrun ? 'scan-progress__budget scan-progress__budget--overrun' : 'scan-progress__budget';
      budgetPart = (
        <span className={cls}>
          {formatClock(dim.elapsedS)} / {formatClock(dim.budgetS)} budget
        </span>
      );
    } else if (dim.elapsedS != null) {
      budgetPart = <span className="scan-progress__budget">{formatClock(dim.elapsedS)}</span>;
    }
    meta = (
      <>
        {`${taken} / ${total}`}
        {dim.activeAgents > 0 && <> · {dim.activeAgents} agents</>}
        {dim.violations > 0 && <> · <span className="scan-progress__v">{dim.violations}v</span></>}
        {dim.compliance > 0 && <> · <span className="scan-progress__c">{dim.compliance}c</span></>}
        {budgetPart && <> · {budgetPart}</>}
      </>
    );
  }

  const fillClass = isDone ? 'scan-progress__bar-fill--done' : '';

  return (
    <div className={`scan-progress__dim${isPending ? ' scan-progress__dim--pending' : ''}`}>
      <span className={`scan-progress__dim-icon ${iconClass}`}>{icon}</span>
      <span className="scan-progress__dim-name">{dim.id}</span>
      <div className="scan-progress__bar">
        <div className={`scan-progress__bar-fill ${fillClass}`} style={{ width: `${p}%` }} />
      </div>
      <span className="scan-progress__dim-meta">{meta}</span>
    </div>
  );
}

function ConsoleButton({ open, showDot, onToggle }) {
  return (
    <button
      type="button"
      className={`scan-progress__console-btn${open ? ' scan-progress__console-btn--open' : ''}`}
      onClick={(e) => { e.stopPropagation(); onToggle(); }}
      aria-label={open ? 'Hide console' : 'Show console'}
      aria-expanded={open}
      title={open ? 'Hide console' : 'Show console'}
    >
      <svg className="scan-progress__console-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="1" y="2" width="14" height="12" rx="2" />
        <polyline points="4.5,6.5 7,9 4.5,11.5" />
        <line x1="9" y1="11" x2="12" y2="11" />
      </svg>
      <span className="scan-progress__console-caret">{open ? '▾' : '▸'}</span>
      {showDot && !open && <span className="scan-progress__console-dot" />}
    </button>
  );
}

export default function ScanProgress({ job, hasEvaluations = false }) {
  const jobId = job?.jobId;
  const status = job?.status;
  const isRunning = status === 'running';
  const isFailed = status === 'failed';
  const isLost = status === 'lost';

  const [progress, setProgress] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [showDot, setShowDot] = useState(() => {
    if (hasEvaluations) return false;
    try { return !localStorage.getItem(CONSOLE_DOT_DISMISSED_KEY); } catch { return true; }
  });
  const timerRef = useRef(null);
  const isTerminal = TERMINAL_STATES.has(status);

  useEffect(() => {
    if (!jobId) return undefined;
    let stopped = false;

    async function tick() {
      try {
        const data = await getEvaluationProgress(jobId);
        if (!stopped) setProgress(data);
      } catch {
        /* progress is best-effort */
      }
    }

    tick();
    if (!isTerminal) {
      timerRef.current = setInterval(tick, POLL_INTERVAL_MS);
    }
    return () => {
      stopped = true;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [jobId, isTerminal]);

  if (!jobId) return null;

  const dims = progress?.dimensions || [];
  // Per-dim file totals are *not* comparable across dims at runtime:
  // running dims expose the post-filter queue size while pending dims
  // fall back to the project-wide ceiling (see scan_progress.py:248-249).
  // Summing them inflates the headline by ~N× the project file count.
  // Use the run's project_files for a stable, intuitive denominator and
  // derive the numerator from the overall work-unit ratio so the
  // displayed `taken / total` matches the overall percentage.
  const projectFiles = progress?.projectFiles ?? 0;
  const workTotal = dims.reduce((acc, d) => acc + (d.files?.total ?? 0), 0);
  const workTaken = dims.reduce((acc, d) => acc + (d.files?.taken ?? 0), 0);
  const overallPct = pct(workTaken, workTotal);
  const totalFiles = projectFiles;
  const takenFiles = projectFiles > 0 && workTotal > 0
    ? Math.round((workTaken / workTotal) * projectFiles)
    : 0;
  const inlineLabel = progress?.currentDimension
    ? <>running <span className="scan-progress__dim-active">{progress.currentDimension}</span></>
    : progress?.phase
      ? <>phase: <span className="scan-progress__dim-active">{progress.phase}</span></>
      : null;

  function toggleDetail() {
    setDetailOpen((v) => !v);
  }
  function toggleConsole() {
    setConsoleOpen((v) => !v);
    if (showDot) {
      setShowDot(false);
      try { localStorage.setItem(CONSOLE_DOT_DISMISSED_KEY, '1'); } catch { /* ignore */ }
    }
  }

  // Failed / lost: show the error message inline above the progress bar.
  const errorBanner = isFailed
    ? <div className="scan-progress__error">{lastRelevantLog(job.logs) || 'Analysis failed'}</div>
    : isLost
      ? <div className="scan-progress__error">Server restarted — job tracking lost</div>
      : null;

  return (
    <div className="scan-progress">
      {errorBanner}
      <div className="scan-progress__row">
        <div className="scan-progress__bar-wrap">
          <div className="scan-progress__bar">
            <div className="scan-progress__bar-fill" style={{ width: `${overallPct}%` }} />
          </div>
          <div className="scan-progress__meta">
            <span>
              {totalFiles > 0 ? <><strong>{takenFiles} / {totalFiles}</strong> files · {overallPct}%</> : <strong>preparing…</strong>}
              {isRunning && inlineLabel && <> · {inlineLabel}</>}
            </span>
            {progress?.totalElapsedS != null && (
              <span><strong>{formatClock(progress.totalElapsedS)}</strong> total</span>
            )}
          </div>
        </div>
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
                  button (and therefore the progress bar to its left) doesn't
                  reflow when toggling between "details" and "hide". */}
              <span className="scan-progress__detail-label-ghost" aria-hidden="true">details</span>
              <span className="scan-progress__detail-label-active">{detailOpen ? 'hide' : 'details'}</span>
            </span>
            <span className={`scan-progress__caret${detailOpen ? ' scan-progress__caret--open' : ''}`} aria-hidden="true">▸</span>
          </button>
          <ConsoleButton open={consoleOpen} showDot={showDot} onToggle={toggleConsole} />
        </div>
      </div>
      {detailOpen && dims.length > 0 && (
        <div className="scan-progress__expanded" id={`scan-progress-detail-${jobId}`}>
          <div className="scan-progress__expanded-label">Per-dimension</div>
          {(() => {
            // Best estimate for pending dims: the largest queue total observed
            // among dims that have actually started (running or done). Falls
            // back to whatever total the backend gave (project-wide ceiling).
            const observed = dims
              .filter((d) => d.state !== 'pending')
              .map((d) => d.files?.total ?? 0)
              .filter((n) => n > 0);
            const fallbackTotal = observed.length > 0 ? Math.max(...observed) : 0;
            return dims.map((d) => <DimRow key={d.id} dim={d} fallbackTotal={fallbackTotal} />);
          })()}
        </div>
      )}
      {consoleOpen && <ConsoleLogViewer logs={job.logs} />}
    </div>
  );
}
