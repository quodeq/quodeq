/**
 * The score-history chart itself, shared by the three panels that draw one:
 * Overview's RunHistoryPanel, the History tab's HistoryChartPanel and the
 * Explorer's DimensionScoreHistoryPanel.
 *
 * All three render the same recharts composition — dashed reference lines, a
 * grade-coloured bar per point, an accent trend line over them — and differ
 * only in the tooltip, whether they fill an area under the line, whether the
 * selected point gets a dot, and how tall the chart is. Those are props.
 *
 * The panel chrome around it — header, period selector, stats line, tooltip
 * cards and the keyboard-controls pairing — is scoreChartPanel.jsx.
 */
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
import {
  cssVar,
  scoreBarColor,
  refLineValues,
  CHART_MARGIN,
  SELECTED_BAR_OPACITY,
  DESELECTED_BAR_OPACITY,
  HOVER_STROKE_WIDTH,
  REF_LINE_OPACITY_EVEN,
  REF_LINE_OPACITY_ODD,
} from './scoreChartHelpers.js';
import { SCORE_SCALE_MAX } from '../constants.js';

// Bars are read as a fraction of a full 0-10 score, so the axis is absolute
// rather than fitted to the data (see RunHistoryPanel's note).
const SCORE_AXIS_DOMAIN = [0, SCORE_SCALE_MAX];
const SELECTED_DOT_RADIUS = 4;
const TREND_LINE_STROKE_WIDTH = 2;
const TREND_LINE_OPACITY = 0.9;
const AREA_TOP_OPACITY = 0.08;
const TOOLTIP_OFFSET = 20;

/**
 * The dot marking the selected run on the trend line. Renders nothing for
 * every other point, which is how recharts draws a single-point marker.
 */
export function SelectedDot({ cx, cy, payload, selectedRunId }) {
  if (payload?.runId !== selectedRunId) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={SELECTED_DOT_RADIUS}
      fill={cssVar('--color-chart-line')}
      stroke="white"
      strokeWidth={HOVER_STROKE_WIDTH}
    />
  );
}

// Not components: recharts finds <Cell> and <ReferenceLine> children by
// inspecting <Bar>'s / the chart's immediate JSX children, so wrapping them in
// a component would hide them and the bars would fall back to a default fill.
function renderScoreBarCells(data, selectedRunId, hoveredIndex) {
  return data.map((entry, i) => (
    <Cell
      key={entry.runId ?? i}
      fill={scoreBarColor(entry.numericAverage)}
      opacity={entry.runId === selectedRunId ? SELECTED_BAR_OPACITY : DESELECTED_BAR_OPACITY}
      stroke={hoveredIndex === i ? cssVar('--color-chart-stroke') : 'none'}
      strokeWidth={hoveredIndex === i ? HOVER_STROKE_WIDTH : 0}
    />
  ));
}

function renderScoreReferenceLines() {
  return refLineValues(SCORE_AXIS_DOMAIN).map((y, i) => (
    <ReferenceLine
      key={y}
      y={y}
      stroke={cssVar('--color-chart-axis')}
      strokeDasharray="4 4"
      strokeOpacity={i % 2 ? REF_LINE_OPACITY_ODD : REF_LINE_OPACITY_EVEN}
    />
  ));
}

function renderAreaGradient(gradientId) {
  return (
    <defs>
      <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={cssVar('--color-accent')} stopOpacity={AREA_TOP_OPACITY} />
        <stop offset="100%" stopColor={cssVar('--color-accent')} stopOpacity={0} />
      </linearGradient>
    </defs>
  );
}

// Hit-detection lives on the chart, not on the Bar: the Area gradient and the
// Line stroke layer over the bars and would swallow the click before it
// reached them. Recharts already resolves the nearest category for us as
// `activeTooltipIndex` on the chart-level events.
function makeChartClickHandler(data, onActivate) {
  return (state) => {
    const idx = state?.activeTooltipIndex;
    if (idx == null) return;
    const point = data[idx];
    if (point?.runId) onActivate(point);
  };
}

/**
 * The score-history chart.
 *
 * @param {Object} props
 * @param {Array} props.data Chart points, oldest first, each with runId/dateLabel/numericAverage.
 * @param {number} props.height Chart height in px; a minimum when `fillHeight` is set.
 * @param {boolean} [props.fillHeight] Stretch to the container instead of fixing the height.
 * @param {number} props.maxBarSize Widest a bar may draw.
 * @param {string} [props.gradientId] Draw a filled area under the line, using this gradient id.
 * @param {React.ReactElement} props.tooltip The panel's tooltip content element.
 * @param {boolean} [props.showSelectedDot] Mark the selected run on the trend line.
 * @param {number|null} props.hoveredIndex
 * @param {(index: number|null) => void} props.setHoveredIndex
 * @param {string|null} props.selectedRunId
 * @param {((point: Object) => void)|undefined} props.onActivate Called with the clicked point, when clicking is enabled.
 */
export function ScoreHistoryChart({
  data, height, fillHeight, maxBarSize, gradientId, tooltip, showSelectedDot,
  hoveredIndex, setHoveredIndex, selectedRunId, onActivate,
}) {
  const handleClick = onActivate ? makeChartClickHandler(data, onActivate) : undefined;
  return (
    <ResponsiveContainer
      width="100%"
      height={fillHeight ? '100%' : height}
      minHeight={fillHeight ? height : undefined}
    >
      <ComposedChart
        data={data}
        margin={CHART_MARGIN}
        onMouseMove={(state) => setHoveredIndex(state?.activeTooltipIndex ?? null)}
        onMouseLeave={() => setHoveredIndex(null)}
        onClick={handleClick}
        style={onActivate ? { cursor: 'pointer' } : undefined}
      >
        {gradientId ? renderAreaGradient(gradientId) : null}
        {/* Axes and grid are deliberately hidden: the panel header carries the
            numbers, and the chart reads as clean edge-to-edge bars. */}
        <XAxis dataKey="dateLabel" hide />
        <YAxis domain={SCORE_AXIS_DOMAIN} hide />
        <Tooltip cursor={false} isAnimationActive={false} offset={TOOLTIP_OFFSET} content={tooltip} />
        {renderScoreReferenceLines()}
        {gradientId ? (
          <Area dataKey="numericAverage" type="monotone" fill={`url(#${gradientId})`} stroke="none" isAnimationActive={false} />
        ) : null}
        <Bar dataKey="numericAverage" radius={[0, 0, 0, 0]} maxBarSize={maxBarSize} isAnimationActive={false}>
          {renderScoreBarCells(data, selectedRunId, hoveredIndex)}
        </Bar>
        <Line
          isAnimationActive={false}
          dataKey="numericAverage"
          type="monotone"
          stroke={cssVar('--color-accent')}
          strokeOpacity={TREND_LINE_OPACITY}
          strokeWidth={TREND_LINE_STROKE_WIDTH}
          dot={showSelectedDot ? <SelectedDot selectedRunId={selectedRunId} /> : false}
          activeDot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
