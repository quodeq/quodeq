import { useState, useEffect } from 'react';
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

// Module-level CSS variable cache. Use clearCssVarCache() for test resets.
const _cssVarCache = new Map();
const cssVar = (name, fallback) => {
  if (_cssVarCache.has(name)) return _cssVarCache.get(name) || fallback;
  const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  _cssVarCache.set(name, val);
  return val || fallback;
};
new MutationObserver(() => _cssVarCache.clear()).observe(
  document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] },
);

/** Clear the CSS variable cache; exported for test resets. */
export function clearCssVarCache() { _cssVarCache.clear(); }

const SCORE_THRESHOLDS = { exemplary: 9, good: 7, adequate: 5, poor: 3 };
const CHART_LEFT_MARGIN = -16;
const CHART_HEIGHT = 160;
const CHART_MAX_BAR_SIZE = 40;
const CHART_CELL_OPACITY = 0.85;
const CHART_Y_TICKS = [0, 2.5, 5, 7.5, 10];
const CHART_BAR_RADIUS = [3, 3, 0, 0];
const TREND_UP_ANGLE = 70;
const TREND_SOFT_UP = 88;
const TREND_DOWN = 110;
const TREND_SOFT_DOWN = 92;

function scoreBarColor(score) {
  const n = parseFloat(score);
  if (isNaN(n)) return cssVar('--color-accent');
  if (n >= SCORE_THRESHOLDS.exemplary) return cssVar('--color-grade-top-text');
  if (n >= SCORE_THRESHOLDS.good) return cssVar('--color-grade-high-text');
  if (n >= SCORE_THRESHOLDS.adequate) return cssVar('--color-grade-mid-text');
  if (n >= SCORE_THRESHOLDS.poor) return cssVar('--color-grade-low-text');
  return cssVar('--color-grade-bottom-text');
}

function trendColorClass(angle) {
  if (angle <= TREND_UP_ANGLE)  return 'trend-up';
  if (angle <= TREND_SOFT_UP)   return 'trend-soft-up';
  if (angle >= TREND_DOWN)      return 'trend-down';
  if (angle >= TREND_SOFT_DOWN) return 'trend-soft-down';
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
      <span className="rht-grade">{gradeLetter(d.overallGrade)}</span>
    </div>
  );
}


function prepareDimensionData(dimensions) {
  return [...dimensions]
    .sort((a, b) => a.dimension.localeCompare(b.dimension))
    .map((d) => {
      const curr = parseFloat(d.overallScore);
      const prev = parseFloat(d.previousScore);
      const delta = !isNaN(curr) && !isNaN(prev) ? curr - prev : null;
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
}

function DimensionBarChart({ data, onBarClick }) {
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
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
          domain={[0, 10]}
          ticks={CHART_Y_TICKS}
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
    <section className="run-history-panel panel" aria-label="Dimension scores bar chart">
      <div className="run-history-header">
        <span className="run-history-title">Dimension Scores</span>
        {(runDate || runId) && (
          <span className="dim-panel-run-meta">
            {runDate && <span className="dim-panel-run-date">{formatShortDate(runDate)}</span>}
            {runId && <span className="dim-panel-run-id">{runId}</span>}
          </span>
        )}
      </div>
      <DimensionBarChart data={data} onBarClick={onBarClick} />
    </section>
  );
}
