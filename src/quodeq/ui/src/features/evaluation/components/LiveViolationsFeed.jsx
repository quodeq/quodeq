import { memo, useState, useMemo, useCallback, useRef } from 'react';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import { FindingDetailBody } from '../../../components/findingDetail.jsx';
import { parseFileRef } from '../../../utils/formatters.js';
import { SectionLabel, SevBadge } from '../../../components/terminal/index.js';
import { useEvaluationProgress } from '../hooks/useEvaluationProgress.js';
import { useDimensionActivity } from '../hooks/useDimensionActivity.js';
import { orderDimensions, sortBySeverity, sameDim } from './liveViolationsOrdering.js';
import LiveFindingsTicker from './LiveFindingsTicker.jsx';
import VirtualList, { useDashboardScrollElement, useScrollMargin } from '../../explorer/components/VirtualList.jsx';
import { t } from '../../../strings/index.js';
import { severityLabel } from '../../../strings/labels.js';
import { JOB_STATUS } from '../../../vocab/jobStatus.js';
import { DIM_STATE } from '../../../vocab/dimState.js';
import { SEVERITY_ORDER } from '../../../vocab/severity.js';
import { KEY } from '../../../vocab/keyboard.js';
import { pluralKey } from '../../../utils/plural.js';

// A collapsed row: 38px min-height plus its 1px border. The virtualizer
// measures the real height, this only sizes rows it has not mounted yet.
const ROW_HEIGHT_ESTIMATE = 39;
// The 3 real severities (as opposed to a missing/unrecognised one), for
// deciding whether SevBadge (which only knows those 3) can render this row.
const REAL_SEVERITY_SET = new Set(SEVERITY_ORDER);

// Open state lives in the group, not here: the virtual list unmounts rows
// scrolled out of view, and a row would come back closed.
const ViolationLiveRow = memo(function ViolationLiveRow({ violation, rowKey, open, onToggle }) {
  const v = violation;
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (v.endLine && v.endLine !== line) ? `${line}-${v.endLine}` : line;
  const ref = line != null ? `${filePath}:${range}` : filePath;
  const display = line != null ? `${filename}:${range}` : filename;

  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`}>
      <div
        className="vdetail-row-main vlive-collapsible"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label={t('evaluate.findingAria', { severity: severityLabel(v.severity), title: v.title || v.file || t('evaluate.detailsFallback') })}
        onClick={() => onToggle(rowKey)}
        onKeyDown={(e) => { if (e.key === KEY.ENTER || e.key === ' ') { e.preventDefault(); onToggle(rowKey); } }}
      >
        <span className="vlive-rail" aria-hidden="true" />
        {REAL_SEVERITY_SET.has(v.severity)
          ? <SevBadge level={v.severity} format="long" />
          : <span className={`severity-tag ${v.severity}`}>{severityLabel(v.severity)}</span>}
        <span className="vrow-rule">{v.principle || ''}</span>
        {filename ? <FileCopyBtn display={display} copyText={ref} /> : <span />}
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
    return <ViolationLiveRow violation={v} rowKey={key} open={expanded.has(key)} onToggle={toggleRow} />;
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

// Every group starts closed and stays that way until the user opens it.
// Several can be open at once; nothing opens on its own.
function useOpenDims() {
  const [openDims, setOpenDims] = useState(() => new Set());
  const toggle = useCallback((dim) => setOpenDims((cur) => {
    const next = new Set(cur);
    if (next.has(dim)) next.delete(dim); else next.add(dim);
    return next;
  }), []);
  return [openDims, toggle];
}

function computeQueuedFiles(runningDim) {
  return runningDim?.files
    ? Math.max(0, (runningDim.files.total ?? 0) - (runningDim.files.taken ?? 0))
    : null;
}

function LiveViolationsHead({ totalCount, orderedDimsCount, hiddenCarriedCount, passedCount, isRunning, currentDimension }) {
  return (
    <div className="vlive-head">
      <span className="vlive-head-left">
        <SectionLabel>{t('evaluate.liveViolationsLabel')}</SectionLabel>
        <span className="vlive-counter">
          {totalCount > 0
            ? t(
              pluralKey(orderedDimsCount, 'evaluate.acrossDimsOne', 'evaluate.acrossDimsMany'),
              { count: totalCount, dims: orderedDimsCount },
            )
            : t('evaluate.noNewFindings')}
          {/* The console line prints "40 v · 1056 c". Saying the passing
              checks here keeps the feed from reading as the run's whole
              output: the rows are the violations, this is the rest. */}
          {passedCount > 0 && (
            <span className="vlive-counter-passed"> · {t(pluralKey(passedCount, 'evaluate.checksPassedOne', 'evaluate.checksPassedMany'), { count: passedCount })}</span>
          )}
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

function LiveViolationsCard({ orderedDims, openDims, toggleDim, currentDimension, isRunning, queued }) {
  return (
    <div className="vlive-card">
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
  // Compliance counts come from the same tally the console heartbeat prints
  // (scan progress), not from the finding stream, which carries violations only.
  const passedCount = (progress?.dimensions || []).reduce((sum, d) => sum + (d?.compliance ?? 0), 0);
  const orderedDims = useMemo(() => orderDimensions(liveViolations, lastActivity, currentDimension),
    // lastActivity is a ref's current value — it's intentionally not in deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [liveViolations, currentDimension]);

  const [openDims, toggleDim] = useOpenDims();

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
        passedCount={passedCount}
        isRunning={isRunning}
        currentDimension={currentDimension}
      />
      {(totalCount > 0 || isRunning) && (
        <>
          <LiveFindingsTicker liveViolations={liveViolations} isRunning={isRunning} />
          <LiveViolationsCard
            orderedDims={orderedDims}
            openDims={openDims}
            toggleDim={toggleDim}
            currentDimension={currentDimension}
            isRunning={isRunning}
            queued={queued}
          />
        </>
      )}
    </div>
  );
}
