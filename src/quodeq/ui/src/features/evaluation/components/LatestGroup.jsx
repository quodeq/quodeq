import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import { FindingDetailBody } from '../../../components/findingDetail.jsx';
import { parseFileRef } from '../../../utils/formatters.js';
import { SevBadge } from '../../../components/terminal/index.js';
import { latestFindings, countFindings, addPin } from './liveTicker.js';
import { t } from '../../../strings/index.js';
import { severityLabel } from '../../../strings/labels.js';
import { SEVERITY_ORDER } from '../../../vocab/severity.js';
import { KEY } from '../../../vocab/keyboard.js';

// One update per window at most, so a burst of findings reads as a few
// steps instead of a flicker.
const TICKER_THROTTLE_MS = 250;
const REAL_SEVERITY_SET = new Set(SEVERITY_ORDER);

function fileRef(v) {
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (v.endLine && v.endLine !== line) ? `${line}-${v.endLine}` : line;
  return {
    filename,
    ref: line != null ? `${filePath}:${range}` : filePath,
    display: line != null ? `${filename}:${range}` : filename,
  };
}

/**
 * A finding's cells, shared by the latest rows and the dimension rows: the
 * severity, the principle (its dimension in the tooltip), the title, the
 * file.
 */
export function FindingCells({ dim, v }) {
  const { filename, ref, display } = fileRef(v);
  return (
    <>
      <span className="vlive-rail" aria-hidden="true" />
      {REAL_SEVERITY_SET.has(v.severity)
        ? <SevBadge level={v.severity} format="long" />
        : <span className={`severity-tag ${v.severity}`}>{severityLabel(v.severity)}</span>}
      <span className="vticker-dim" title={dim}>{v.principle || dim}</span>
      <span className="vrow-rule">{v.title || ''}</span>
      {filename ? <FileCopyBtn display={display} copyText={ref} /> : <span />}
    </>
  );
}

// Holds the last value shown while `frozen`, and otherwise lets a new value
// through at most once per `ms`.
function useThrottledValue(value, ms, frozen) {
  const [shown, setShown] = useState(value);
  const lastRef = useRef(0);
  useEffect(() => {
    if (frozen || shown === value) return undefined;
    const wait = Math.max(0, lastRef.current + ms - Date.now());
    const id = setTimeout(() => { lastRef.current = Date.now(); setShown(value); }, wait);
    return () => clearTimeout(id);
  }, [value, ms, frozen, shown]);
  return shown;
}

// Rows on screen at the first render are already "there"; only the ones
// that arrive after it slide in.
function useArrivedKeys(rows) {
  const seenRef = useRef(null);
  if (seenRef.current === null) seenRef.current = new Set(rows.map((r) => r.key));
  const arrived = new Set(rows.filter((r) => !seenRef.current.has(r.key)).map((r) => r.key));
  useEffect(() => { for (const r of rows) seenRef.current.add(r.key); }, [rows]);
  return arrived;
}

function TickerRow({ row, pinned, arrived, onPin }) {
  const { v } = row;
  const pin = () => onPin(row);
  return (
    <div className={`vdetail-row vdetail-row--${v.severity} vticker-row${arrived ? ' vticker-row--enter' : ''}${pinned ? ' vticker-row--pinned' : ''}`}>
      <div
        className="vdetail-row-main vlive-collapsible vticker-row-main"
        role="button"
        tabIndex={0}
        aria-pressed={pinned}
        aria-label={t('evaluate.pinFindingAria', { severity: severityLabel(v.severity), title: v.title || v.file || t('evaluate.detailsFallback') })}
        onClick={pin}
        onKeyDown={(e) => { if (e.key === KEY.ENTER || e.key === ' ') { e.preventDefault(); pin(); } }}
      >
        <FindingCells dim={row.dim} v={v} />
      </div>
    </div>
  );
}

function PinnedFinding({ row, onUnpin }) {
  return (
    <div className={`vticker-pin vdetail-row--${row.v.severity}`}>
      <div className="vticker-pin-main">
        <FindingCells dim={row.dim} v={row.v} />
        <button type="button" className="vticker-unpin" onClick={() => onUnpin(row.key)} aria-label={t('evaluate.unpinFinding')}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true" focusable="false">
            <line x1="6" y1="6" x2="18" y2="18" /><line x1="18" y1="6" x2="6" y2="18" />
          </svg>
        </button>
      </div>
      <FindingDetailBody v={row.v} />
    </div>
  );
}

function TickerState({ isRunning, paused, waiting }) {
  if (!isRunning) return null;
  let label = t('evaluate.tickerLive');
  if (paused) label = waiting > 0 ? t('evaluate.tickerPausedWaiting', { count: waiting }) : t('evaluate.tickerPaused');
  return (
    <span className={`vticker-state${paused ? ' vticker-state--paused' : ''}`}>
      <span className="vlive-footer__dot" aria-hidden="true" />
      {label}
    </span>
  );
}

// Pauses while the pointer or keyboard focus is inside, so a row does not
// slide away from under the click meant for it.
function usePauseOnHover() {
  const [paused, setPaused] = useState(false);
  const handlers = useMemo(() => ({
    onPointerEnter: () => setPaused(true),
    onPointerLeave: () => setPaused(false),
    onFocus: () => setPaused(true),
    onBlur: (e) => { if (!e.currentTarget.contains(e.relatedTarget)) setPaused(false); },
  }), []);
  return [paused, handlers];
}

/**
 * The first group of the live findings accordion: the latest findings across
 * every dimension, newest on top. Clicking one pins it, with its detail, at
 * the top of the group until it is closed. No count: the feed head and the
 * tiles already say how many. `passed` (a diff review's checks passed) fills
 * the group while it has nothing to list.
 */
export default function LatestGroup({ liveViolations, isRunning, open, onToggle, passed = null }) {
  const [paused, hoverHandlers] = usePauseOnHover();
  const [pins, setPins] = useState([]);
  const latest = useMemo(() => latestFindings(liveViolations), [liveViolations]);
  const total = countFindings(liveViolations);
  const shown = useThrottledValue(latest, TICKER_THROTTLE_MS, paused);
  const shownTotalRef = useRef(total);
  if (!paused) shownTotalRef.current = total;
  const arrived = useArrivedKeys(shown);
  const pinnedKeys = new Set(pins.map((p) => p.key));
  // One pinned finding: a new pin replaces it.
  const onPin = useCallback((row) => setPins((cur) => addPin(cur, row, 1)), []);
  const onUnpin = useCallback((key) => setPins((cur) => cur.filter((p) => p.key !== key)), []);

  return (
    <div className={`vlive-dimension-group vlatest-group${open ? '' : ' vlive-dimension-group--collapsed'}`}>
      <button type="button" className="vlive-dimension-label" onClick={onToggle} aria-expanded={open}>
        <span className={`vlive-dimension-caret${open ? ' vlive-dimension-caret--open' : ''}`} aria-hidden="true">▸</span>
        <span className="vlive-dimension-name">{t('evaluate.latestFindings')}</span>
        <TickerState isRunning={isRunning} paused={paused} waiting={total - shownTotalRef.current} />
      </button>
      {/* Hidden with the group, back when it opens again. */}
      {open && pins.length > 0 && (
        <div className="vticker-pins" aria-label={t('evaluate.pinnedFindings')}>
          {pins.map((row) => <PinnedFinding key={row.key} row={row} onUnpin={onUnpin} />)}
        </div>
      )}
      {open && shown.length === 0 && passed != null && (
        <div className="vlatest-empty">{t('evaluate.latestEmptyPassed', { count: passed })}</div>
      )}
      {open && shown.length > 0 && (
        <div className="vlatest-rows" {...hoverHandlers}>
          {shown.map((row) => (
            <TickerRow key={row.key} row={row} pinned={pinnedKeys.has(row.key)} arrived={arrived.has(row.key)} onPin={onPin} />
          ))}
        </div>
      )}
    </div>
  );
}
