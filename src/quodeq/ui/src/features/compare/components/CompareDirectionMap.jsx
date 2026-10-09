/**
 * Where each project stands and where it is heading: a quadrant chart with
 * 0 movement as the vertical axis (exact centre) and the fleet average as
 * the horizontal one. Up is score, right is 30-day improvement, dot size is
 * files, colour is grade; below the average is shaded at every size (a
 * small weak project is not better off for being small). Flat is normal,
 * so a steady band sits around 0, and only the corners that need a
 * reaction are labelled. Projects with no runs in 30 days are listed as
 * chips under the chart, not parked on 0. Geometry: compareDirectionMap.js.
 */
import { t } from '../../../strings/index.js';
import { scoreColorClass, scoreGradeColorVar } from '../../../utils/formatters.js';
import { buildDirectionMap } from '../compareDirectionMap.js';
import { useMeasuredWidth } from '../hooks/useMeasuredWidth.js';
import { nf, score1, signed1 } from '../compareFormatters.js';

const HEIGHT = 320;
const PAD = Object.freeze({ left: 16, right: 16, top: 18, bottom: 18 });
const FALLBACK_WIDTH = 640;
const TICK_HALF = 3;
const TICK_LABEL_GAP = 6;
const MOVE_LABEL_DY = 14;
const CORNER_INSET = 6;
const CORNER_BASELINE = 12;
const AXIS_LABEL_DY = 4;
const LEGEND_DOT_SMALL = 3.5;
const LEGEND_DOT_BIG = 6.5;

function Frame({ m, box }) {
  const right = box.left + box.width;
  const bottom = box.top + box.height;
  return (
    <g>
      <rect className="compare-dirmap__below" x={box.left} y={m.center.y} width={box.width} height={bottom - m.center.y} />
      <rect className="compare-dirmap__steady" x={m.steady.x1} y={box.top} width={m.steady.x2 - m.steady.x1} height={box.height} />
      <text className="compare-dirmap__corner compare-dirmap__corner--watch" x={box.left + CORNER_INSET} y={box.top + CORNER_BASELINE}>{t('compare.mapWatch')}</text>
      <text className="compare-dirmap__corner compare-dirmap__corner--act" x={box.left + CORNER_INSET} y={bottom - CORNER_INSET}>{t('compare.mapAct')}</text>
      <text className="compare-dirmap__corner" x={right - CORNER_INSET} y={bottom - CORNER_INSET} textAnchor="end">{t('compare.mapRecover')}</text>
      <line className="compare-dirmap__axis" x1={box.left} x2={right} y1={m.center.y} y2={m.center.y} />
      <line className="compare-dirmap__axis" x1={m.center.x} x2={m.center.x} y1={box.top} y2={bottom} />
      {m.ticks.score.map((tk) => (
        <g key={tk.v}>
          <line className="compare-dirmap__axis" x1={m.center.x - TICK_HALF} x2={m.center.x + TICK_HALF} y1={tk.y} y2={tk.y} />
          <text className="compare-dirmap__tick" x={m.center.x - TICK_LABEL_GAP} y={tk.y + TICK_HALF} textAnchor="end">{tk.v}</text>
        </g>
      ))}
      {m.ticks.move.map((tk) => (
        <g key={tk.d}>
          <line className="compare-dirmap__axis" x1={tk.x} x2={tk.x} y1={m.center.y - TICK_HALF} y2={m.center.y + TICK_HALF} />
          <text className="compare-dirmap__tick" x={tk.x} y={m.center.y + MOVE_LABEL_DY} textAnchor="middle">{signed1(tk.d)}</text>
        </g>
      ))}
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
  return (
    <g
      className={`compare-dirmap__pt${on ? ' is-on' : ''}${hover && !on ? ' is-dim' : ''}`}
      {...linked(row.id, setHover, onOpenProject)}
    >
      <circle cx={p.cx} cy={p.cy} r={p.r} className="compare-dirmap__dot" style={{ '--dot': scoreGradeColorVar(row.score) }} />
      <text className="compare-dirmap__name" x={p.label.x} y={p.label.y} textAnchor={p.label.anchorEnd ? 'end' : 'start'}>
        {row.name}
        {row.stale && <tspan className="compare-dirmap__stale">{t('compare.mapStaleTag')}</tspan>}
      </text>
      <title>{t('compare.mapPointTip', { name: row.name, score: score1(row.score), move: signed1(row.delta), files: nf(row.totalFiles ?? 0) })}</title>
    </g>
  );
}

function Still({ rows, hover, setHover, onOpenProject }) {
  if (!rows.length) return null;
  return (
    <div className="compare-dirmap__still">
      <span className="compare-dirmap__stillLabel">{t('compare.mapStill')}</span>
      {rows.map((row) => (
        <button
          key={row.id}
          type="button"
          className={`compare-dirmap__chip${hover === row.id ? ' is-on' : ''}`}
          {...linked(row.id, setHover, onOpenProject)}
        >
          <span className="compare-dirmap__chipDot" style={{ '--dot': scoreGradeColorVar(row.score) }} aria-hidden="true" />
          {row.name}
          <span className={scoreColorClass(row.score)}>{score1(row.score)}</span>
        </button>
      ))}
    </div>
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
      <span><span className="compare-dirmap__legendStale">{t('compare.mapLegendStale')}</span> {t('compare.mapLegendStaleValue')}</span>
      <span><span className="compare-dirmap__legendBelow" />{key(t('compare.mapLegendShaded'), t('compare.mapLegendShadedValue'))}</span>
    </div>
  );
}

export default function CompareDirectionMap({ rows, fleetScore, hover, setHover, onOpenProject }) {
  const [ref, width] = useMeasuredWidth(FALLBACK_WIDTH);
  const box = { left: PAD.left, top: PAD.top, width: width - PAD.left - PAD.right, height: HEIGHT - PAD.top - PAD.bottom };
  const m = buildDirectionMap({ rows, fleetScore, box });
  const pointProps = { hover, setHover, onOpenProject };
  return (
    <div ref={ref} className="compare-dirmap">
      <svg width={width} height={HEIGHT} role="img" aria-label={t('compare.mapAria')}>
        <Frame m={m} box={box} />
        <text className="compare-dirmap__axisLabel" x={m.center.x + TICK_LABEL_GAP} y={box.top + AXIS_LABEL_DY}>{t('compare.mapScoreAxis')}</text>
        <text className="compare-dirmap__axisLabel" x={box.left + box.width} y={m.center.y - TICK_LABEL_GAP} textAnchor="end">
          {t('compare.mapMoveAxis', { score: score1(fleetScore) })}
        </text>
        {m.points.map((p) => <Point key={p.row.id} p={p} {...pointProps} />)}
      </svg>
      <Still rows={m.still} {...pointProps} />
      <Legend />
    </div>
  );
}
