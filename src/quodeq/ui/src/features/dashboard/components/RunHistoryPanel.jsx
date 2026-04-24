import { useState, useMemo } from 'react';
import { gradeLetter, scoreColorClass } from '../../../utils/formatters.js';
import { SectionLabel } from '../../../components/terminal/index.js';
import {
  ComposedChart,
  Area,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';

const MAX_CHART_RUNS = 20;
const CHART_HEIGHT = 160;
const REF_LINE_LOW = 2.5;
const REF_LINE_MID = 5;
const REF_LINE_HIGH = 7.5;
/* Margin zeroed so bars span edge-to-edge inside the panel body. */
const CHART_MARGIN = { top: 8, right: 0, bottom: 0, left: 0 };

// Module-level CSS variable cache. Cleared automatically by MutationObserver
// when the data-theme attribute changes. Use clearCssVarCache() for test resets.
const _cssVarCache = new Map();
const cssVar = (name, fallback) => {
  if (_cssVarCache.has(name)) return _cssVarCache.get(name);
  if (typeof document === 'undefined') return fallback;
  const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const result = val || fallback;
  _cssVarCache.set(name, result);
  return result;
};

/** Clear the CSS variable cache. Called automatically by MutationObserver on theme change; exported for test resets. */
export function clearCssVarCache() { _cssVarCache.clear(); }

// Auto-clear cache when theme changes (data-theme attribute mutation)
if (typeof document !== 'undefined') {
  new MutationObserver(() => _cssVarCache.clear()).observe(
    document.documentElement,
    { attributes: true, attributeFilter: ['data-theme'] },
  );
}

const GRADE_CSS_VARS = {
  'grade-top':    '--color-grade-top-text',
  'grade-high':   '--color-grade-high-text',
  'grade-mid':    '--color-grade-mid-text',
  'grade-low':    '--color-grade-low-text',
  'grade-bottom': '--color-grade-bottom-text',
  'grade-none':   '--color-text-muted',
};

// Bar color follows the active theme's grade spectrum — flynn renders cyan→red,
// daruma renders gold→crimson, neo renders matrix-green→red, etc. Each theme's
// `--color-grade-*-text` tokens map through `scoreColorClass` into the 5-step
// spectrum defined in tokens.css.
function scoreBarColor(score) {
  const varName = GRADE_CSS_VARS[scoreColorClass(score)] || '--color-accent';
  return cssVar(varName);
}


function buildTrendData(trend, selectedRunId) {
  return [...trend].slice(0, MAX_CHART_RUNS).reverse().map((row, i, arr) => {
    const numericAverage = parseFloat(row.numericAverage);
    return {
      ...row,
      numericAverage,
      delta: i > 0 ? numericAverage - parseFloat(arr[i - 1].numericAverage) : null,
    };
  });
}


function RunHistoryTooltip({ active, hoveredIndex, data }) {
  if (!active || hoveredIndex === null) return null;
  const entry = data[hoveredIndex];
  if (!entry) return null;
  return (
    <div className="run-history-tooltip">
      <span className="rht-date">{entry.dateLabel}</span>
      <span className="rht-score">{entry.numericAverage.toFixed(1)} / 10</span>
      <span className="rht-grade">{gradeLetter(entry.overallGrade)}</span>
    </div>
  );
}

function SelectedDot({ cx, cy, payload, selectedRunId }) {
  if (payload?.runId !== selectedRunId) return null;
  return <circle cx={cx} cy={cy} r={4} fill={cssVar('--color-chart-line')} stroke="white" strokeWidth={1.5} />;
}

function ScoreBars({ data, hoveredIndex, setHoveredIndex, selectedRunId, onBarClick }) {
  return (
    <Bar
      dataKey="numericAverage"
      radius={[0, 0, 0, 0]}
      maxBarSize={28}
      isAnimationActive={false}
      cursor={onBarClick ? 'pointer' : 'default'}
      onMouseEnter={(_, index) => setHoveredIndex(index)}
      onMouseLeave={() => setHoveredIndex(null)}
      onClick={(entry) => onBarClick?.(entry.runId)}
    >
      {data.map((entry, i) => (
        <Cell
          key={entry.runId ?? i}
          fill={scoreBarColor(entry.numericAverage)}
          opacity={entry.runId === selectedRunId ? 0.85 : 0.4}
          stroke={hoveredIndex === i ? cssVar('--color-chart-stroke') : 'none'}
          strokeWidth={hoveredIndex === i ? 1.5 : 0}
        />
      ))}
    </Bar>
  );
}

function ScoreHistoryChart({ data, interaction }) {
  const { hoveredIndex, setHoveredIndex, selectedRunId, onBarClick } = interaction;
  return (
    <ResponsiveContainer width="100%" height="100%" minHeight={CHART_HEIGHT}>
      <ComposedChart data={data} margin={CHART_MARGIN}>
        <defs>
          <linearGradient id="scoreAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={cssVar('--color-accent')} stopOpacity={0.08} />
            <stop offset="100%" stopColor={cssVar('--color-accent')} stopOpacity={0} />
          </linearGradient>
        </defs>
        {/* Axes/grid/reference lines intentionally omitted — the mockup shows
            clean edge-to-edge bars with just the accent-coloured trend line
            on top. Labels live in the banner (MIN / MAX / AVG). */}
        <XAxis dataKey="dateLabel" hide />
        <YAxis domain={[0, 10]} hide />
        <Tooltip cursor={false} isAnimationActive={false} offset={20} content={({ active }) => <RunHistoryTooltip active={active} hoveredIndex={hoveredIndex} data={data} />} />
        {/* Soft horizontal reference lines at 25% / 50% / 75% of the range —
            kept as subtle grid anchors even though the numeric ticks are
            hidden. */}
        <ReferenceLine y={REF_LINE_LOW}  stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <ReferenceLine y={REF_LINE_MID}  stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <ReferenceLine y={REF_LINE_HIGH} stroke={cssVar('--color-chart-axis')} strokeDasharray="4 4" strokeOpacity={0.45} />
        <Area dataKey="numericAverage" type="monotone" fill="url(#scoreAreaGrad)" stroke="none" isAnimationActive={false} />
        <ScoreBars data={data} hoveredIndex={hoveredIndex} setHoveredIndex={setHoveredIndex} selectedRunId={selectedRunId} onBarClick={onBarClick} />
        <Line isAnimationActive={false} dataKey="numericAverage" type="monotone" stroke={cssVar('--color-accent')} strokeOpacity={0.9} strokeWidth={2} dot={<SelectedDot selectedRunId={selectedRunId} />} activeDot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function RunHistoryPanel({ trend = [], selectedRunId = null, onBarClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null);
  // Hooks must run in the same order every render, so compute before any early return.
  const data = useMemo(() => buildTrendData(trend, selectedRunId), [trend, selectedRunId]);

  if (!trend || trend.length < 2) return null;

  const min = Math.min(...data.map((d) => d.numericAverage).filter((n) => !Number.isNaN(n)));
  const max = Math.max(...data.map((d) => d.numericAverage).filter((n) => !Number.isNaN(n)));
  const avg = data.reduce((s, d) => s + (Number.isNaN(d.numericAverage) ? 0 : d.numericAverage), 0) / data.length;

  return (
    <section className="run-history-panel run-history-panel--terminal panel" aria-label="Score history chart">
      <div className="run-history-panel__header">
        <SectionLabel>score_history · {data.length}d</SectionLabel>
        <span className="run-history-panel__stats">
          MIN {min.toFixed(1)} / MAX {max.toFixed(1)} / AVG {avg.toFixed(1)}
        </span>
      </div>
      <ScoreHistoryChart
        data={data}
        interaction={{ hoveredIndex, setHoveredIndex, selectedRunId, onBarClick }}
      />
    </section>
  );
}
