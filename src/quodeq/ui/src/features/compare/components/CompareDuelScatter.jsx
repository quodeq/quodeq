/**
 * Principle scatter for the head-to-head: side A's score across, side B's
 * up, one dot per principle both scored. On the dashed diagonal the two are
 * equal; the shaded band around it is "even"; the shaded corner is where
 * both are below good. Dots take the colour of the side that leads.
 * Hovering a dot (or its row in the lists beside it) highlights both.
 */
import { t } from '../../../strings/index.js';
import { EVEN_BAND } from '../compareDuelAnalysis.js';
import { DUEL_SIDE } from '../duelTrendGeometry.js';
import { score1 } from './compareDuelShared.jsx';
import { SCORE_SCALE_MAX } from '../../../constants.js';

const SIZE = 300;
const PAD = 34;
const DOT_R = 4.5;
const DOT_R_ON = 6.5;
// Tick every point, or every other one when the axis starts low.
const DENSE_FROM = 4;
const LOW_MARGIN = 0.5;
const TICK_BELOW = 14;
const TICK_LEFT = 8;
const TICK_BASELINE = 4;
const AXIS_INSET = 6;
const AXIS_ABOVE = 14;
const AXIS_BELOW = 4;
const NOTE_INSET = 4;

const EVEN = 'even';

function axis(points, good) {
  const low = Math.max(0, Math.floor(Math.min(good, ...points.flatMap((p) => [p.a, p.b])) - LOW_MARGIN));
  const span = SIZE - 2 * PAD;
  const at = (v) => PAD + ((v - low) / (SCORE_SCALE_MAX - low)) * span;
  const ticks = [];
  for (let v = low; v <= SCORE_SCALE_MAX; v += low < DENSE_FROM ? 2 : 1) ticks.push(v);
  return { low, at, ay: (v) => SIZE - at(v), ticks, band: (EVEN_BAND / (SCORE_SCALE_MAX - low)) * span };
}

function sideOf(p) {
  if (Math.abs(p.gap) < EVEN_BAND) return EVEN;
  return p.gap > 0 ? DUEL_SIDE.A : DUEL_SIDE.B;
}

function Frame({ ax, good, aName, bName }) {
  const { low, at, ay, band } = ax;
  const hi = SCORE_SCALE_MAX;
  const bandPoints = [
    [at(low), ay(low) - band], [at(hi) - band, ay(hi)], [at(hi), ay(hi)],
    [at(hi), ay(hi) + band], [at(low) + band, ay(low)], [at(low), ay(low)],
  ].map((q) => q.join(',')).join(' ');
  return (
    <g>
      <rect className="compare-duel-scatter__weak" x={at(low)} y={ay(good)} width={at(good) - at(low)} height={ay(low) - ay(good)} />
      <polygon className="compare-duel-scatter__band" points={bandPoints} />
      {ax.ticks.map((v) => (
        <g key={v}>
          <line className="compare-duel-scatter__grid" x1={at(v)} x2={at(v)} y1={ay(low)} y2={ay(hi)} />
          <line className="compare-duel-scatter__grid" x1={at(low)} x2={at(hi)} y1={ay(v)} y2={ay(v)} />
          <text className="compare-duel-scatter__tick" x={at(v)} y={SIZE - PAD + TICK_BELOW} textAnchor="middle">{v}</text>
          <text className="compare-duel-scatter__tick" x={PAD - TICK_LEFT} y={ay(v) + TICK_BASELINE} textAnchor="end">{v}</text>
        </g>
      ))}
      <line className="compare-duel-scatter__diag" x1={at(low)} y1={ay(low)} x2={at(hi)} y2={ay(hi)} />
      <text className="compare-duel-scatter__axis compare-duel__ink--a" x={SIZE - PAD} y={SIZE - AXIS_BELOW} textAnchor="end">{t('compare.duelMapAxisA', { name: aName })}</text>
      <text className="compare-duel-scatter__axis compare-duel__ink--b" x={AXIS_INSET} y={PAD - AXIS_ABOVE}>{t('compare.duelMapAxisB', { name: bName })}</text>
      <text className="compare-duel-scatter__note" x={at(low) + NOTE_INSET} y={ay(low) - AXIS_INSET}>{t('compare.duelMapWeakZone')}</text>
    </g>
  );
}

export default function CompareDuelScatter({ map, aName, bName, hover, setHover }) {
  const ax = axis(map.points, map.good);
  return (
    <svg
      className="compare-duel-scatter"
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="img"
      aria-label={t('compare.duelMapChartAria', { a: aName, b: bName })}
    >
      <Frame ax={ax} good={map.good} aName={aName} bName={bName} />
      {map.points.map((p) => {
        const on = hover === p.id;
        return (
          <circle
            key={p.id}
            cx={ax.at(p.a)}
            cy={ax.ay(p.b)}
            r={on ? DOT_R_ON : DOT_R}
            className={`compare-duel-scatter__dot compare-duel-scatter__dot--${sideOf(p)}${hover && !on ? ' compare-duel-scatter__dot--dim' : ''}`}
            onMouseEnter={() => setHover(p.id)}
            onMouseLeave={() => setHover(null)}
          >
            <title>{t('compare.duelMapPointTip', { principle: p.label, dimension: p.dimLabel, a: score1(p.a), b: score1(p.b) })}</title>
          </circle>
        );
      })}
    </svg>
  );
}
