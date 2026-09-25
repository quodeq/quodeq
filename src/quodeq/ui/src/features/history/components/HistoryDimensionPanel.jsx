import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';
import { formatShortDate, angleFromDelta, gradeLetter } from '../../../utils/formatters.js';
import ChartKeyboardControls from '../../../components/ChartKeyboardControls.jsx';
import { cssVar, PANEL_CHART_HEIGHT_PX } from '../../../components/scoreChartHelpers.js';
import { fallbackDelta } from '../../../utils/dimensionUtils.js';
import { t } from '../../../strings/index.js';
import { scoreBarColorVar } from './scoreBarColor.js';
import { SCORE_SCALE_MAX } from '../../../constants.js';

const CHART_LEFT_MARGIN = -16;
const CHART_MAX_BAR_SIZE = 40;
const CHART_CELL_OPACITY = 0.85;
const CHART_Y_TICK_QUARTER = 2.5;
const CHART_Y_TICK_HALF = 5;
const CHART_Y_TICK_THREE_QUARTER = 7.5;
const CHART_Y_TICKS = [0, CHART_Y_TICK_QUARTER, CHART_Y_TICK_HALF, CHART_Y_TICK_THREE_QUARTER, SCORE_SCALE_MAX];
const CHART_BAR_CORNER_RADIUS = 3;
const CHART_BAR_RADIUS = [CHART_BAR_CORNER_RADIUS, CHART_BAR_CORNER_RADIUS, 0, 0];
const TREND_UP_ANGLE = 70;
const TREND_SOFT_UP = 88;
const TREND_DOWN = 110;
const TREND_SOFT_DOWN = 92;
// Fallback shortcode length for a dimension name not in DIM_CODE.
const FALLBACK_DIM_CODE_LENGTH = 4;
// Trend label placement: the delta text sits above the arrow glyph.
const DELTA_LABEL_Y_OFFSET = 25;
const ARROW_LABEL_Y_OFFSET = 14;

function scoreBarColor(score) {
  return cssVar(scoreBarColorVar(score));
}

function trendColorClass(angle) {
  if (angle <= TREND_UP_ANGLE)  return 'trend-up';
  if (angle <= TREND_SOFT_UP)   return 'trend-soft-up';
  if (angle >= TREND_DOWN)      return 'trend-down';
  if (angle >= TREND_SOFT_DOWN) return 'trend-soft-down';
  return 'trend-same';
}

// Shortcodes mirror src/quodeq/config/dimensions.py.
// Ideally these would come from a /api/dimensions config endpoint;
// hardcoded for now to avoid an extra network round-trip.
const DIM_CODE = {
  affordability:  'aff',
  availability:   'avl',
  configurability:'cfg',
  efficiency:     'eff',
  evolvability:   'evo',
  extensibility:  'ext',
  flexibility:    'flx',
  maintainability:'mnt',
  performance:    'perf',
  recoverability: 'rcv',
  resilience:     'res',
  robustness:     'rob',
  scalability:    'scl',
  simplicity:     'sim',
  usability:      'usx',
};

function dimCode(name) {
  if (!name) return '';
  return (DIM_CODE[name.toLowerCase()] ?? name.slice(0, FALLBACK_DIM_CODE_LENGTH)).toUpperCase();
}

function trendColorVar(colorClass) {
  const map = {
    'trend-up':        '--color-trend-up',
    'trend-soft-up':   '--color-trend-soft-up',
    'trend-same':      '--color-text-muted',
    'trend-soft-down': '--color-trend-soft-down',
    'trend-down':      '--color-trend-down',
  };
  return cssVar(map[colorClass] || '--color-text-muted');
}

function DimensionTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="run-history-tooltip">
      <span className="rht-date">{d.dimension}</span>
      <span className="rht-score">{t('history.outOfTen', { score: parseFloat(d.overallScore).toFixed(1) })}</span>
      <span className="rht-grade">{gradeLetter(d.overallGrade)}</span>
    </div>
  );
}


function prepareDimensionData(dimensions) {
  return [...dimensions]
    .sort((a, b) => a.dimension.localeCompare(b.dimension))
    .map((d) => {
      const curr = parseFloat(d.overallScore);
      const delta = fallbackDelta(d);
      return { ...d, numericScore: isNaN(curr) ? 0 : curr, delta };
    });
}

function renderTrendLabel(data, { x, y, width, index }) {
  const entry = data[index];
  if (entry?.delta === null || entry?.delta === undefined) return null;
  const cx = x + width / 2;
  const angle = angleFromDelta(entry.delta);
  const colorCls = trendColorClass(angle);
  const fill = trendColorVar(colorCls);
  const deltaStr = entry.delta > 0 ? `+${entry.delta.toFixed(1)}` : entry.delta.toFixed(1);
  return (
    <g>
      <text x={cx} y={y - DELTA_LABEL_Y_OFFSET} textAnchor="middle" fontSize={9} fill={fill}>
        {deltaStr}
      </text>
      <text
        x={cx} y={y - ARROW_LABEL_Y_OFFSET}
        textAnchor="middle" fontSize={11} fill={fill}
        transform={`rotate(${Math.round(angle)}, ${cx}, ${y - ARROW_LABEL_Y_OFFSET})`}
      >
        ↑
      </text>
    </g>
  );
}

function DimensionBarChart({ data, onBarClick }) {
  return (
    <ResponsiveContainer width="100%" height={PANEL_CHART_HEIGHT_PX}>
      <BarChart data={data} margin={{ top: 32, right: 8, bottom: 0, left: CHART_LEFT_MARGIN }}>
        <CartesianGrid vertical={false} stroke={cssVar('--color-chart-grid')} />
        <XAxis
          dataKey="dimension"
          tickFormatter={dimCode}
          tick={{ fontSize: 11, fill: cssVar('--color-chart-axis') }}
          interval={0}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          domain={[0, SCORE_SCALE_MAX]}
          ticks={CHART_Y_TICKS}
          tick={{ fontSize: 11, fill: cssVar('--color-chart-axis') }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={DimensionTooltip} cursor={false} isAnimationActive={false} />
        <ReferenceLine y={CHART_Y_TICK_QUARTER} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.15} />
        <ReferenceLine y={CHART_Y_TICK_HALF}    stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.3} />
        <ReferenceLine y={CHART_Y_TICK_THREE_QUARTER} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.15} />
        <Bar
          dataKey="numericScore"
          radius={CHART_BAR_RADIUS}
          maxBarSize={CHART_MAX_BAR_SIZE}
          label={(props) => renderTrendLabel(data, props)}
          isAnimationActive={false}
          cursor={onBarClick ? 'pointer' : 'default'}
          onClick={(entry) => onBarClick?.(entry)}
        >
          {data.map((entry, i) => (
            <Cell
              key={entry.dimension ?? i}
              fill={scoreBarColor(entry.numericScore)}
              opacity={CHART_CELL_OPACITY}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function DimensionScorePanel({ dimensions = [], onBarClick, runDate, runId }) {
  if (!dimensions || dimensions.length === 0) return null;

  const data = prepareDimensionData(dimensions);

  return (
    <section className="run-history-panel panel" aria-label={t('history.dimensionScoresAria')}>
      <div className="run-history-header">
        <span className="run-history-title">{t('history.dimensionScoresTitle')}</span>
        {(runDate || runId) && (
          <span className="dim-panel-run-meta">
            {runDate && <span className="dim-panel-run-date">{formatShortDate(runDate)}</span>}
            {runId && <span className="dim-panel-run-id">{runId}</span>}
          </span>
        )}
      </div>
      <div className="chart-with-kbd">
        <DimensionBarChart data={data} onBarClick={onBarClick} />
        <ChartKeyboardControls
          label={t('history.kbdDimsLabel')}
          items={onBarClick ? data.map((d, i) => ({
            key: d.dimension ?? i,
            text: t('history.kbdDimItem', { dimension: d.dimension, score: Number.isFinite(d.numericScore) ? d.numericScore.toFixed(1) : '?', grade: gradeLetter(d.overallGrade) }),
            onActivate: () => onBarClick(d),
          })) : []}
        />
      </div>
    </section>
  );
}
