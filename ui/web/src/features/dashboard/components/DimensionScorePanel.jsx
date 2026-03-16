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
import { formatShortDate } from '../../../utils/formatters.js';

function cssVar(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function scoreBarColor(score) {
  const n = parseFloat(score);
  if (isNaN(n)) return cssVar('--color-accent');
  if (n >= 9) return cssVar('--color-grade-top-text');   // exemplary
  if (n >= 7) return cssVar('--color-grade-high-text');  // good
  if (n >= 5) return cssVar('--color-grade-mid-text');   // adequate
  if (n >= 3) return cssVar('--color-grade-low-text');   // poor
  return cssVar('--color-grade-bottom-text');            // critical
}

// Rotation: 0° = straight up (↑), 90° = horizontal (→), 180° = straight down (↓)
// sqrt curve: non-zero deltas always tilt; max arc 55° keeps small changes subtle
function angleFromDelta(d) {
  const clamped = Math.max(-4, Math.min(4, d));
  return 90 - Math.sign(clamped) * Math.sqrt(Math.abs(clamped) / 4) * 55;
}

function trendColorClass(angle) {
  if (angle <= 70)  return 'trend-up';
  if (angle <= 88)  return 'trend-soft-up';
  if (angle >= 110) return 'trend-down';
  if (angle >= 92)  return 'trend-soft-down';
  return 'trend-same';
}

// Shortcodes mirror src/quodeq/config/dimensions.py
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
  return (DIM_CODE[name.toLowerCase()] ?? name.slice(0, 4)).toUpperCase();
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
      <span className="rht-score">{parseFloat(d.overallScore).toFixed(1)} / 10</span>
      <span className="rht-grade">{d.overallGrade}</span>
    </div>
  );
}


export default function DimensionScorePanel({ dimensions = [], onBarClick, runDate, runId }) {
  if (!dimensions || dimensions.length === 0) return null;

  const data = [...dimensions]
    .sort((a, b) => a.dimension.localeCompare(b.dimension))
    .map((d) => {
      const curr = parseFloat(d.overallScore);
      const prev = parseFloat(d.previousScore);
      const delta = !isNaN(curr) && !isNaN(prev) ? curr - prev : null;
      return { ...d, numericScore: isNaN(curr) ? 0 : curr, delta };
    });

  const renderTrendLabel = ({ x, y, width, index }) => {
    const entry = data[index];
    if (entry?.delta === null || entry?.delta === undefined) return null;
    const cx = x + width / 2;
    const angle = angleFromDelta(entry.delta);
    const colorCls = trendColorClass(angle);
    const fill = trendColorVar(colorCls);
    const deltaStr = entry.delta > 0 ? `+${entry.delta.toFixed(1)}` : entry.delta.toFixed(1);
    return (
      <g>
        <text x={cx} y={y - 25} textAnchor="middle" fontSize={9} fill={fill}>
          {deltaStr}
        </text>
        <text
          x={cx} y={y - 14}
          textAnchor="middle" fontSize={11} fill={fill}
          transform={`rotate(${Math.round(angle)}, ${cx}, ${y - 14})`}
        >
          ↑
        </text>
      </g>
    );
  };

  return (
    <section className="run-history-panel panel">
      <div className="run-history-header">
        <span className="run-history-title">Dimension Scores</span>
        {(runDate || runId) && (
          <span className="dim-panel-run-meta">
            {runDate && <span className="dim-panel-run-date">{formatShortDate(runDate)}</span>}
            {runId && <span className="dim-panel-run-id">{runId}</span>}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={data} margin={{ top: 32, right: 8, bottom: 0, left: -16 }}>
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
            domain={[0, 10]}
            ticks={[0, 2.5, 5, 7.5, 10]}
            tick={{ fontSize: 11, fill: cssVar('--color-chart-axis') }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={DimensionTooltip} cursor={false} isAnimationActive={false} />
          <ReferenceLine y={2.5} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.15} />
          <ReferenceLine y={5}   stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.3} />
          <ReferenceLine y={7.5} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.15} />
          <Bar
            dataKey="numericScore"
            radius={[3, 3, 0, 0]}
            maxBarSize={40}
            label={renderTrendLabel}
            isAnimationActive={false}
            cursor={onBarClick ? 'pointer' : 'default'}
            onClick={(entry) => onBarClick?.(entry)}
          >
            {data.map((entry, i) => (
              <Cell
                key={entry.dimension ?? i}
                fill={scoreBarColor(entry.numericScore)}
                opacity={0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
