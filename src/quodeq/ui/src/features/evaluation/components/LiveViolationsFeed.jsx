import { useState, useMemo, useRef, useEffect } from 'react';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import { parseFileRef } from '../../../utils/formatters.js';
import { SectionLabel, SevBadge } from '../../../components/terminal/index.js';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';
import { useDimensionActivity } from '../hooks/useDimensionActivity.js';
import { orderDimensions } from './liveViolationsOrdering.js';
import { t } from '../../../strings/index.js';
import { severityLabel } from '../../../strings/labels.js';

const ANIM_DELAY_PER_ITEM_MS = 40;
const ANIM_MAX_DELAY_MS = 400;
const KNOWN_SEVERITIES = new Set(['critical', 'major', 'minor']);

function ViolationDetail({ v }) {
  return (
    <div className="vlive-detail">
      {(v.title || v.reason) && (
        <div className="vlive-detail-section">
          <div className="vlive-detail-section-header">
            <span className="vlive-detail-section-label">{t('violations.reasonLabel')}</span>
            {(() => {
              const urlRefs = v.reqRefs?.filter(r => r.url && /^https?:\/\//.test(r.url)) || [];
              return urlRefs.length > 0 && (
                <span className="cwe-link-group">{urlRefs.map((ref, i) => (
                  <a key={i} className="cwe-link" href={ref.url} target="_blank" rel="noopener noreferrer">{ref.label}</a>
                ))}</span>
              );
            })()}
          </div>
          {v.title && <p className="vlive-detail-title">{v.title}</p>}
          {v.reason && <>
            <span className="vlive-detail-section-label">{t('violations.detailLabel')}</span>
            <p className="vlive-detail-reason">{v.reason}</p>
          </>}
        </div>
      )}
      <ContextBlock context={v.context} snippet={v.snippet} scope={v.scope} line={v.line} endLine={v.endLine} />
    </div>
  );
}

function ViolationLiveRow({ violation, index }) {
  const [open, setOpen] = useState(false);
  const v = violation;
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (v.endLine && v.endLine !== line) ? `${line}-${v.endLine}` : line;
  const ref = line != null ? `${filePath}:${range}` : filePath;
  const display = line != null ? `${filename}:${range}` : filename;

  return (
    <div
      className={`vdetail-row vdetail-row--${v.severity}`}
      style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}
    >
      <div
        className="vdetail-row-main vlive-collapsible"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label={t('evaluate.findingAria', { severity: severityLabel(v.severity), title: v.title || v.file || t('evaluate.detailsFallback') })}
        onClick={() => setOpen(o => !o)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(o => !o); } }}
      >
        <span className="vlive-rail" aria-hidden="true" />
        {KNOWN_SEVERITIES.has(v.severity)
          ? <SevBadge level={v.severity} format="long" />
          : <span className={`severity-tag ${v.severity}`}>{severityLabel(v.severity)}</span>}
        <span className="vrow-rule">{v.principle || ''}</span>
        {filename ? <FileCopyBtn display={display} copyText={ref} /> : <span />}
        <svg
          className={`vlive-chevron${open ? ' open' : ''}`}
          width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </div>
      {open && <ViolationDetail v={v} />}
    </div>
  );
}

function DimensionGroup({ dim, violations, open, onToggle }) {
  const count = violations.length;
  return (
    <div className={`vlive-dimension-group${open ? '' : ' vlive-dimension-group--collapsed'}`}>
      <button
        type="button"
        className="vlive-dimension-label"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className={`vlive-dimension-caret${open ? ' vlive-dimension-caret--open' : ''}`} aria-hidden="true">▸</span>
        <span className="vlive-dimension-name">{dim}</span>
        <span className="vlive-dimension-count">{count}</span>
      </button>
      {open && violations.map((v, i) => (
        <ViolationLiveRow key={`${dim}-${v.file}-${v.principle}-${String(v.line ?? '')}`} violation={v} index={i} />
      ))}
    </div>
  );
}

// Single-open-at-a-time accordion. The topmost (most recently active) dim
// auto-expands; whenever the topmost changes — i.e. a new dimension starts
// producing violations — the previous one collapses and the new one opens.
// The user can still click any header to switch which one is open.
function useAutoOpenTopDim(orderedDims) {
  const [openDim, setOpenDim] = useState(null);
  const topDim = orderedDims[0]?.dim;
  const prevTopRef = useRef(null);
  useEffect(() => {
    if (topDim && prevTopRef.current !== topDim) {
      prevTopRef.current = topDim;
      setOpenDim(topDim);
    }
  }, [topDim]);
  return [openDim, setOpenDim];
}

function computeQueuedFiles(runningDim) {
  return runningDim?.files
    ? Math.max(0, (runningDim.files.total ?? 0) - (runningDim.files.taken ?? 0))
    : null;
}

function LiveViolationsHead({ totalCount, orderedDimsCount, hiddenCarriedCount, isRunning, currentDimension }) {
  return (
    <div className="vlive-head">
      <span className="vlive-head-left">
        <SectionLabel>{t('evaluate.liveViolationsLabel')}</SectionLabel>
        <span className="vlive-counter">
          {totalCount > 0
            ? (orderedDimsCount === 1
                ? t('evaluate.acrossDimsOne', { count: totalCount, dims: orderedDimsCount })
                : t('evaluate.acrossDimsMany', { count: totalCount, dims: orderedDimsCount }))
            : t('evaluate.noNewFindings')}
          {hiddenCarriedCount > 0 && (
            <span className="vlive-counter-hidden"> · {t('evaluate.carriedForwardHidden', { count: hiddenCarriedCount })}</span>
          )}
          {isRunning && <> · {t('evaluate.streaming')}</>}
        </span>
      </span>
      {isRunning && currentDimension && (
        <span className="vlive-head-dim">{currentDimension}</span>
      )}
    </div>
  );
}

function LiveViolationsCard({ orderedDims, openDim, setOpenDim, isRunning, queued }) {
  return (
    <div className="vlive-card">
      {orderedDims.map(({ dim, violations }) => (
        <DimensionGroup
          key={dim}
          dim={dim}
          violations={violations}
          open={openDim === dim}
          onToggle={() => setOpenDim((cur) => (cur === dim ? null : dim))}
        />
      ))}
      {isRunning && (
        <div className="vlive-footer">
          <span className="vlive-footer__dot" aria-hidden="true" />
          {t('evaluate.scanningForMore')}{queued != null ? <> · {t('evaluate.filesQueued', { count: queued })}</> : null}
        </div>
      )}
    </div>
  );
}

export default function LiveViolationsFeed({ liveViolations, job = null, hiddenCarriedCount = 0 }) {
  // Per-dim activity timestamps power "latest active dimension on top".
  const lastActivity = useDimensionActivity(liveViolations);

  const isRunning = job?.status === 'running';
  // Shares the progress query cache entry with the strip/progress — the hook
  // adds no polling of its own. Only used for the streaming footer/header.
  const { data: progress } = useEvaluationProgress(job?.jobId, !isRunning);
  const runningDim = (progress?.dimensions || []).find((d) => d?.state === 'running');
  const queued = computeQueuedFiles(runningDim);

  const orderedDims = useMemo(() => orderDimensions(liveViolations, lastActivity),
    // lastActivity is a ref's current value — it's intentionally not in deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [liveViolations]);

  const [openDim, setOpenDim] = useAutoOpenTopDim(orderedDims);

  const totalCount = orderedDims.reduce((sum, d) => sum + d.violations.length, 0);
  // A fully-cached dimension yields zero NEW findings. Bailing out here
  // would make the feed disappear and read as "nothing found", so keep the
  // header whenever the filter is what emptied the list.
  if (!totalCount && !hiddenCarriedCount) return null;

  return (
    <div className="vlive-feed">
      <LiveViolationsHead
        totalCount={totalCount}
        orderedDimsCount={orderedDims.length}
        hiddenCarriedCount={hiddenCarriedCount}
        isRunning={isRunning}
        currentDimension={progress?.currentDimension}
      />
      {(totalCount > 0 || isRunning) && (
        <LiveViolationsCard orderedDims={orderedDims} openDim={openDim} setOpenDim={setOpenDim} isRunning={isRunning} queued={queued} />
      )}
    </div>
  );
}
