/**
 * Where each project stands and where it is heading. Up is score, right is
 * 30-day improvement, dot size is files, colour is grade. The view fits the
 * projects, so they fill the plot; the two references are dotted lines
 * wherever they fall, not axes through the middle: "no change" (0
 * movement, with a faint steady band around it) and the fleet average
 * (below it is shaded at every size, a small weak project is not better
 * off for being small). Projects with no runs in 30 days sit on the "no
 * change" line, hollow. Only the corners that need a reaction are
 * labelled, when their side of "no change" has room.
 * Geometry: compareDirectionMap.js.
 */
import { useMemo } from 'react';
import { t } from '../../../strings/index.js';
import { scoreGradeColorVar } from '../../../utils/formatters.js';
import { buildDirectionMap } from '../compareDirectionMap.js';
import { useMeasuredSize } from '../hooks/useMeasuredWidth.js';
import { nf, score1, signed1 } from '../compareFormatters.js';

// The plot fills the height its row gives it (the attention list beside
// it sets the row); the stylesheet bounds that between a floor and a cap.
const FALLBACK_SIZE = Object.freeze({ width: 640, height: 340 });
// Room for the score labels on the left and the movement labels below.
const PAD = Object.freeze({ left: 34, right: 16, top: 22, bottom: 42 });
const TICK_LABEL_GAP = 6;
const MOVE_LABEL_DY = 14;
// The movement caption sits on its own line under the tick values.
const MOVE_CAPTION_DY = 30;
const CORNER_INSET = 6;
const CORNER_BASELINE = 12;
const REF_LABEL_GAP = 4;
const LEGEND_DOT_SMALL = 3.5;
const LEGEND_DOT_BIG = 6.5;
const LEGEND_HOLLOW_R = 5;
// A corner label needs this much room on its side of "no change".
const CORNER_ROOM = 190;
// Centres a 10px tick label on its grid line.
const LABEL_NUDGE = 3;

/* Faint dotted grid at every tick, with the values on the plot's edges. */
function Grid({ m, box }) {
  const right = box.left + box.width;
  const bottom = box.top + box.height;
  return (
    <g>
      {m.ticks.move.map((tk) => (
        <g key={`x${tk.d}`}>
          <line className="compare-dirmap__grid" x1={tk.x} x2={tk.x} y1={box.top} y2={bottom} />
          <text className="compare-dirmap__tick" x={tk.x} y={bottom + MOVE_LABEL_DY} textAnchor="middle">{tk.d === 0 ? '0' : signed1(tk.d)}</text>
        </g>
      ))}
      {m.ticks.score.map((tk) => (
        <g key={`y${tk.v}`}>
          <line className="compare-dirmap__grid" x1={box.left} x2={right} y1={tk.y} y2={tk.y} />
          <text className="compare-dirmap__tick" x={box.left - TICK_LABEL_GAP} y={tk.y + LABEL_NUDGE} textAnchor="end">{score1(tk.v)}</text>
        </g>
      ))}
    </g>
  );
}
/* Slipping is left of "no change", improving right of it: a corner is
   labelled only when its side has room for the words. */
function Corners({ m, box }) {
  const right = box.left + box.width;
  const bottom = box.top + box.height;
  const slipRoom = m.zeroX - box.left >= CORNER_ROOM;
  const recoverRoom = right - m.zeroX >= CORNER_ROOM;
  return (
    <g>
      {slipRoom && <text className="compare-dirmap__corner compare-dirmap__corner--watch" x={box.left + CORNER_INSET} y={box.top + CORNER_BASELINE}>{t('compare.mapWatch')}</text>}
      {slipRoom && <text className="compare-dirmap__corner compare-dirmap__corner--act" x={box.left + CORNER_INSET} y={bottom - CORNER_INSET}>{t('compare.mapAct')}</text>}
      {recoverRoom && <text className="compare-dirmap__corner" x={right - CORNER_INSET} y={bottom - CORNER_INSET} textAnchor="end">{t('compare.mapRecover')}</text>}
    </g>
  );
}

function Frame({ m, box, fleetScore }) {
  const right = box.left + box.width;
  const bottom = box.top + box.height;
  return (
    <g>
      <rect className="compare-dirmap__below" x={box.left} y={m.fleetY} width={box.width} height={bottom - m.fleetY} />
      <rect className="compare-dirmap__steady" x={m.steady.x1} y={box.top} width={Math.max(0, m.steady.x2 - m.steady.x1)} height={box.height} />
      <Grid m={m} box={box} />
      <Corners m={m} box={box} />
      <line className="compare-dirmap__ref" x1={m.zeroX} x2={m.zeroX} y1={box.top} y2={bottom} />
      <text className="compare-dirmap__refLabel" x={m.zeroX + REF_LABEL_GAP} y={box.top - REF_LABEL_GAP}>{t('compare.mapZero')}</text>
      <line className="compare-dirmap__ref" x1={box.left} x2={right} y1={m.fleetY} y2={m.fleetY} />
      <text className="compare-dirmap__refLabel" x={right} y={m.fleetY - REF_LABEL_GAP} textAnchor="end">{t('compare.mapFleetLine', { score: score1(fleetScore) })}</text>
      <text className="compare-dirmap__axisLabel" x={box.left - TICK_LABEL_GAP} y={box.top - REF_LABEL_GAP} textAnchor="end">{t('compare.mapScoreAxis')}</text>
      <text className="compare-dirmap__axisLabel" x={right} y={bottom + MOVE_CAPTION_DY} textAnchor="end">{t('compare.mapMoveAxis')}</text>
    </g>
  );
}

/* Hover lights the project up across the page; a click opens it. */
function linked(id, setHover, onOpenProject) {
  return {
    onMouseEnter: () => setHover(id),
    onMouseLeave: () => setHover(null),
    onClick: () => onOpenProject(id),
  };
}

function Point({ p, hover, setHover, onOpenProject }) {
  const { row } = p;
  const on = hover === row.id;
  const tip = p.still
    ? t('compare.mapStillTip', { name: row.name, score: score1(row.score), files: nf(row.totalFiles ?? 0) })
    : t('compare.mapPointTip', { name: row.name, score: score1(row.score), move: signed1(row.delta), files: nf(row.totalFiles ?? 0) });
  return (
    <g
      className={`compare-dirmap__pt${on ? ' is-on' : ''}${hover && !on ? ' is-dim' : ''}${p.still ? ' is-still' : ''}`}
      {...linked(row.id, setHover, onOpenProject)}
    >
      <circle cx={p.cx} cy={p.cy} r={p.r} className="compare-dirmap__dot" style={{ '--dot': scoreGradeColorVar(row.score) }} />
      <text className="compare-dirmap__name" x={p.label.x} y={p.label.y} textAnchor={p.label.anchorEnd ? 'end' : 'start'}>
        {row.name}
        {row.stale && <tspan className="compare-dirmap__stale">{t('compare.mapStaleTag')}</tspan>}
      </text>
      <title>{tip}</title>
    </g>
  );
}

function Legend() {
  const key = (k, v) => <><b>{k}</b> {v}</>;
  return (
    <div className="compare-dirmap__legend" aria-hidden="true">
      <span>
        <svg className="compare-dirmap__legendSize" viewBox="0 0 30 16" width="30" height="16">
          <circle cx="6" cy="8" r={LEGEND_DOT_SMALL} /><circle cx="21" cy="8" r={LEGEND_DOT_BIG} />
        </svg>
        {key(t('compare.mapLegendSize'), t('compare.mapLegendSizeValue'))}
      </span>
      <span><span className="compare-dirmap__legendGrades" />{key(t('compare.mapLegendColour'), t('compare.mapLegendColourValue'))}</span>
      <span>
        <svg className="compare-dirmap__legendHollow" viewBox="0 0 16 16" width="16" height="16">
          <circle cx="8" cy="8" r={LEGEND_HOLLOW_R} />
        </svg>
        {key(t('compare.mapLegendHollow'), t('compare.mapLegendHollowValue'))}
      </span>
      <span><span className="compare-dirmap__legendStale">{t('compare.mapLegendStale')}</span> {t('compare.mapLegendStaleValue')}</span>
      <span><span className="compare-dirmap__legendBelow" />{key(t('compare.mapLegendShaded'), t('compare.mapLegendShadedValue'))}</span>
    </div>
  );
}

export default function CompareDirectionMap({ rows, fleetScore, hover, setHover, onOpenProject }) {
  const [ref, { width, height }] = useMeasuredSize(FALLBACK_SIZE);
  const box = useMemo(() => ({ left: PAD.left, top: PAD.top, width: width - PAD.left - PAD.right, height: height - PAD.top - PAD.bottom }), [width, height]);
  // Hovering anywhere on the page re-renders the map (the hover state is
  // shared): rebuild the geometry only when its inputs change.
  const m = useMemo(() => buildDirectionMap({ rows, fleetScore, box }), [rows, fleetScore, box]);
  const pointProps = { hover, setHover, onOpenProject };
  return (
    <div className="compare-dirmap">
      <div ref={ref} className="compare-dirmap__plot">
        <svg width={width} height={height} role="img" aria-label={t('compare.mapAria')}>
          <Frame m={m} box={box} fleetScore={fleetScore} />
          {m.points.map((p) => <Point key={p.row.id} p={p} {...pointProps} />)}
        </svg>
      </div>
      <Legend />
    </div>
  );
}
