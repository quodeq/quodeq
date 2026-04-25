import { useEffect, useRef, useState } from 'react';
import { getEvaluationProgress } from '../../../api/index.js';

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATES = new Set(['done', 'failed', 'cancelled']);

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

function DimRow({ dim }) {
  const taken = dim.files?.taken ?? 0;
  const total = dim.files?.total ?? 0;
  const p = pct(taken, total);
  const isDone = dim.state === 'done';
  const isRunning = dim.state === 'running';
  const isPending = dim.state === 'pending';

  const isPartial = isDone && total > 0 && taken < total;

  let icon = '○';
  let iconClass = '';
  if (isDone) {
    icon = isPartial ? '◐' : '✓';
    iconClass = isPartial ? 'scan-progress__dim-icon--partial' : 'scan-progress__dim-icon--done';
  } else if (isRunning) {
    icon = '▶';
    iconClass = 'scan-progress__dim-icon--running';
  }

  let meta;
  if (isPending) {
    meta = <span className="scan-progress__dim-meta-pending">pending</span>;
  } else if (isDone) {
    meta = (
      <>
        {isPartial ? (
          <>
            {`${taken} / ${total}`} · <span className="scan-progress__partial">partial</span>
          </>
        ) : (
          total > 0 ? `${total} files` : ''
        )}
        {dim.violations > 0 && <> · <span className="scan-progress__v">{dim.violations}v</span></>}
        {dim.compliance > 0 && <> · <span className="scan-progress__c">{dim.compliance}c</span></>}
        {dim.elapsedS != null && <> · {formatClock(dim.elapsedS)}</>}
      </>
    );
  } else {
    // running
    let budgetPart;
    if (dim.budgetS) {
      const overrun = dim.elapsedS != null && dim.elapsedS > dim.budgetS;
      const cls = overrun ? 'scan-progress__budget scan-progress__budget--overrun' : 'scan-progress__budget';
      budgetPart = (
        <span className={cls}>
          {formatClock(dim.elapsedS)} / {formatClock(dim.budgetS)} budget
        </span>
      );
    } else {
      budgetPart = <span className="scan-progress__budget">{formatClock(dim.elapsedS)}</span>;
    }
    meta = (
      <>
        {`${taken} / ${total}`}
        {dim.activeAgents > 0 && <> · {dim.activeAgents} agents</>}
        {dim.violations > 0 && <> · <span className="scan-progress__v">{dim.violations}v</span></>}
        {dim.compliance > 0 && <> · <span className="scan-progress__c">{dim.compliance}c</span></>}
        {' · '}
        {budgetPart}
      </>
    );
  }

  const fillClass = isDone
    ? (isPartial ? 'scan-progress__bar-fill--partial' : 'scan-progress__bar-fill--done')
    : '';

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

export default function ScanProgress({ jobId, status }) {
  const [progress, setProgress] = useState(null);
  const [open, setOpen] = useState(false);
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
        // ignore — progress is best-effort
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

  if (!progress) return null;

  const dims = progress.dimensions || [];
  const totalFiles = dims.reduce((acc, d) => acc + (d.files?.total ?? 0), 0);
  const takenFiles = dims.reduce((acc, d) => acc + (d.files?.taken ?? 0), 0);
  const overallPct = pct(takenFiles, totalFiles);
  const phaseLabel = progress.currentDimension
    ? <>running <span className="scan-progress__dim-active">{progress.currentDimension}</span></>
    : progress.phase
      ? <>phase: <span className="scan-progress__dim-active">{progress.phase}</span></>
      : null;

  return (
    <div className="scan-progress">
      <button
        type="button"
        className="scan-progress__row"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={`scan-progress-detail-${jobId}`}
      >
        <div className="scan-progress__bar-wrap">
          <div className="scan-progress__bar">
            <div className="scan-progress__bar-fill" style={{ width: `${overallPct}%` }} />
          </div>
          <div className="scan-progress__meta">
            <span>
              <strong>{takenFiles} / {totalFiles}</strong> files · {overallPct}%
              {phaseLabel && <> · {phaseLabel}</>}
            </span>
            {progress.totalElapsedS != null && (
              <span><strong>{formatClock(progress.totalElapsedS)}</strong> total</span>
            )}
          </div>
        </div>
        <span className={`scan-progress__caret${open ? ' scan-progress__caret--open' : ''}`} aria-hidden="true">▸</span>
      </button>
      {open && (
        <div className="scan-progress__expanded" id={`scan-progress-detail-${jobId}`}>
          <div className="scan-progress__expanded-label">Per-dimension</div>
          {dims.map((d) => <DimRow key={d.id} dim={d} />)}
        </div>
      )}
    </div>
  );
}
