import { memo, useState, useMemo, useCallback, useRef } from 'react';
import { FindingDetailBody } from '../../../components/findingDetail.jsx';
import { SectionLabel, SevBadge } from '../../../components/terminal/index.js';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';
import { useDimensionActivity } from '../hooks/useDimensionActivity.js';
import { orderDimensions, sortBySeverity, sameDim } from './liveViolationsOrdering.js';
import LatestGroup, { FindingCells } from './LatestGroup.jsx';
import VirtualList, { useDashboardScrollElement, useScrollMargin } from '../../explorer/components/VirtualList.jsx';
import { t } from '../../../strings/index.js';
import { severityLabel } from '../../../strings/labels.js';
import { JOB_STATUS } from '../../../vocab/jobStatus.js';
import { DIM_STATE } from '../../../vocab/dimState.js';
import { SEVERITY_ORDER } from '../../../vocab/severity.js';
import { KEY } from '../../../vocab/keyboard.js';

// A collapsed row: 38px min-height plus its 1px border. The virtualizer
// measures the real height, this only sizes rows it has not mounted yet.
const ROW_HEIGHT_ESTIMATE = 39;

// Open state lives in the group, not here: the virtual list unmounts rows
// scrolled out of view, and a row would come back closed.
const ViolationLiveRow = memo(function ViolationLiveRow({ dim, violation, rowKey, open, onToggle }) {
  const v = violation;
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`}>
      <div
        className="vdetail-row-main vlive-collapsible vticker-row-main vlive-row--expandable"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label={t('evaluate.findingAria', { severity: severityLabel(v.severity), title: v.title || v.file || t('evaluate.detailsFallback') })}
        onClick={() => onToggle(rowKey)}
        onKeyDown={(e) => { if (e.key === KEY.ENTER || e.key === ' ') { e.preventDefault(); onToggle(rowKey); } }}
      >
        {/* Same shape as the latest rows: principle, then the title. */}
        <FindingCells dim={dim} v={v} />
        <svg
          className={`vlive-chevron${open ? ' open' : ''}`}
          width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round"
          aria-hidden="true" focusable="false"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </div>
      {open && <FindingDetailBody v={v} />}
    </div>
  );
});

function rowKeyOf(dim, v) {
  return `${dim}-${v.arrivalSeq ?? ''}-${v.file}-${v.principle}-${String(v.line ?? '')}`;
}

function severityMix(violations) {
  const mix = { critical: 0, major: 0, minor: 0 };
  for (const v of violations) if (v.severity in mix) mix[v.severity] += 1;
  return mix;
}

function DimensionHeader({ dim, violations, open, scanning, onToggle }) {
  const count = violations.length;
  const mix = severityMix(violations);
  return (
    <button type="button" className="vlive-dimension-label" onClick={onToggle} aria-expanded={open}>
      <span className={`vlive-dimension-caret${open ? ' vlive-dimension-caret--open' : ''}`} aria-hidden="true">▸</span>
      <span className="vlive-dimension-name">{dim}</span>
      {scanning && <span className="vlive-dimension-scanning">{t('evaluate.dimScanning')}</span>}
      <span className="vlive-dimension-mix">
        {SEVERITY_ORDER.map((level) => (mix[level] > 0
          ? <SevBadge key={level} level={level} format="count-abbr" count={mix[level]} />
          : null))}
      </span>
      {/* Keyed on the count so the bump animation replays on every arrival. */}
      <span key={count} className="vlive-dimension-count">{count}</span>
    </button>
  );
}

// Only the rows near the viewport are mounted, however many the dimension
// holds, the same virtual list the Explorer's detail pages use.
function DimensionRows({ dim, violations }) {
  // Sorted only while open: a closed group costs one header however big it is.
  const rows = useMemo(() => sortBySeverity(violations), [violations]);
  const scrollElement = useDashboardScrollElement();
  const listRef = useRef(null);
  const scrollMargin = useScrollMargin(listRef, scrollElement);
  const [expanded, setExpanded] = useState(() => new Set());
  const toggleRow = useCallback((key) => setExpanded((cur) => {
    const next = new Set(cur);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  }), []);
  const getItemKey = useCallback((i) => (rows[i] ? rowKeyOf(dim, rows[i]) : i), [dim, rows]);
  const estimateSize = useCallback(() => ROW_HEIGHT_ESTIMATE, []);
  const renderRow = (v) => {
    const key = rowKeyOf(dim, v);
    return <ViolationLiveRow dim={dim} violation={v} rowKey={key} open={expanded.has(key)} onToggle={toggleRow} />;
  };
  return (
    <div ref={listRef}>
      <VirtualList
        items={rows}
        scrollElement={scrollElement}
        scrollMargin={scrollMargin}
        estimateSize={estimateSize}
        getItemKey={getItemKey}
        renderItem={renderRow}
        label={t('evaluate.dimFindingsList', { dim })}
      />
    </div>
  );
}

// Memoised so a finding landing in one dimension does not re-render the others.
const DimensionGroup = memo(function DimensionGroup({ dim, violations, open, scanning, onToggle }) {
  return (
    <div className={`vlive-dimension-group${open ? '' : ' vlive-dimension-group--collapsed'}`}>
      <DimensionHeader dim={dim} violations={violations} open={open} scanning={scanning} onToggle={() => onToggle(dim)} />
      {open && <DimensionRows dim={dim} violations={violations} />}
    </div>
  );
});

// "latest 10" starts open and every dimension closed. Several dimensions can
// be open at once; opening one closes "latest 10", so one live list leads.
function useOpenDims() {
  const [openDims, setOpenDims] = useState(() => new Set());
  const [latestOpen, setLatestOpen] = useState(true);
  const toggleDim = useCallback((dim) => setOpenDims((cur) => {
    const next = new Set(cur);
    if (next.has(dim)) next.delete(dim);
    else { next.add(dim); setLatestOpen(false); }
    return next;
  }), []);
  const toggleLatest = useCallback(() => setLatestOpen((v) => !v), []);
  return { openDims, toggleDim, latestOpen, toggleLatest };
}

function computeQueuedFiles(runningDim) {
  return runningDim?.files
    ? Math.max(0, (runningDim.files.total ?? 0) - (runningDim.files.taken ?? 0))
    : null;
}

// The head says how many new findings this run has, and that it is still
// streaming. Passed checks are in the progress details; carried-forward
// findings follow the "new findings only" setting.
function LiveViolationsHead({ totalCount, isRunning }) {
  const count = totalCount > 0 ? t('evaluate.newCount', { count: totalCount }) : t('evaluate.noNewFindings');
  return (
    <div className="vlive-head">
      <span className="vlive-head-left">
        <SectionLabel>{t('evaluate.liveViolationsLabel')}</SectionLabel>
        <span className="vlive-counter">{isRunning ? `${count} · ${t('evaluate.streaming')}` : count}</span>
      </span>
    </div>
  );
}

function LiveViolationsCard({ liveViolations, orderedDims, open, currentDimension, isRunning, queued }) {
  const { openDims, toggleDim, latestOpen, toggleLatest } = open;
  return (
    <div className="vlive-card">
      <LatestGroup liveViolations={liveViolations} isRunning={isRunning} open={latestOpen} onToggle={toggleLatest} />
      {orderedDims.map(({ dim, violations }) => (
        <DimensionGroup
          key={dim}
          dim={dim}
          violations={violations}
          open={openDims.has(dim)}
          scanning={isRunning && sameDim(dim, currentDimension)}
          onToggle={toggleDim}
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

  const isRunning = job?.status === JOB_STATUS.RUNNING;
  // Shares the progress query cache entry with the strip/progress — the hook
  // adds no polling of its own. Only used for the streaming footer/header.
  const { data: progress } = useEvaluationProgress(job?.jobId, !isRunning);
  const runningDim = (progress?.dimensions || []).find((d) => d?.state === DIM_STATE.RUNNING);
  const queued = computeQueuedFiles(runningDim);

  const currentDimension = progress?.currentDimension;
  const orderedDims = useMemo(() => orderDimensions(liveViolations, lastActivity, currentDimension),
    // lastActivity is a ref's current value — it's intentionally not in deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [liveViolations, currentDimension]);

  const open = useOpenDims();

  const totalCount = orderedDims.reduce((sum, d) => sum + d.violations.length, 0);
  // A fully-cached dimension yields zero NEW findings. Bailing out here
  // would make the feed disappear and read as "nothing found", so keep the
  // header whenever the filter is what emptied the list.
  if (!totalCount && !hiddenCarriedCount) return null;

  return (
    <div className="vlive-feed">
      <LiveViolationsHead totalCount={totalCount} isRunning={isRunning} />
      {(totalCount > 0 || isRunning) && (
        <LiveViolationsCard
          liveViolations={liveViolations}
          orderedDims={orderedDims}
          open={open}
          currentDimension={currentDimension}
          isRunning={isRunning}
          queued={queued}
        />
      )}
    </div>
  );
}
