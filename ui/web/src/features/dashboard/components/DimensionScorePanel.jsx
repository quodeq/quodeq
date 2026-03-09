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

function cssVar(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

const GRADE_VAR = {
  exemplary:    '--color-grade-top-text',
  good:         '--color-grade-high-text',
  proficient:   '--color-grade-high-text',
  adequate:     '--color-grade-mid-text',
  developing:   '--color-grade-mid-text',
  poor:         '--color-grade-low-text',
  insufficient: '--color-grade-low-text',
  critical:     '--color-grade-bottom-text',
  a: '--color-grade-top-text',
  b: '--color-grade-high-text',
  c: '--color-grade-mid-text',
  d: '--color-grade-low-text',
  f: '--color-grade-bottom-text',
};

function gradeBarColor(grade) {
  if (!grade) return cssVar('--color-accent');
  const key = grade.trim().toLowerCase();
  const varName = GRADE_VAR[key] ?? GRADE_VAR[key.charAt(0)];
  return varName ? cssVar(varName) : cssVar('--color-accent');
}

const TREND_ARROW = { up: '↑', 'soft-up': '↗', same: '→', 'soft-down': '↘', down: '↓' };
const TREND_COLOR = {
  up:         cssVar('--color-trend-up'),
  'soft-up':  cssVar('--color-trend-soft-up'),
  same:       cssVar('--color-text-muted'),
  'soft-down':cssVar('--color-trend-soft-down'),
  down:       cssVar('--color-trend-down'),
};

// Shortcodes mirror src/codecompass/config/dimensions.py
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

function trendDir(delta) {
  if (delta === null || delta === undefined) return null;
  if (delta > 1)    return 'up';
  if (delta > 0.5)  return 'soft-up';
  if (delta < -1)   return 'down';
  if (delta < -0.5) return 'soft-down';
  return 'same';
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


export default function DimensionScorePanel({ dimensions = [], onBarClick }) {
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
    const dir = trendDir(entry?.delta);
    if (!dir) return null;
    const cx = x + width / 2;
    const deltaStr = entry.delta > 0 ? `+${entry.delta.toFixed(1)}` : entry.delta.toFixed(1);
    return (
      <g>
        <text x={cx} y={y - 25} textAnchor="middle" fontSize={9} fill={TREND_COLOR[dir]}>
          {deltaStr}
        </text>
        <text x={cx} y={y - 14} textAnchor="middle" fontSize={11} fill={TREND_COLOR[dir]}>
          {TREND_ARROW[dir]}
        </text>
      </g>
    );
  };

  return (
    <section className="run-history-panel panel">
      <div className="run-history-header">
        <span className="run-history-title">Dimension Scores</span>
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
                fill={gradeBarColor(entry.overallGrade)}
                opacity={0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
