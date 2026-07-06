/**
 * DimensionSparkline — inline SVG sparkline of recent scores for a single
 * dimension. Renders a row of thin vertical bars, one per evaluation, with
 * heights proportional to score and colours drawn from the theme's grade
 * spectrum (`--color-grade-*-text`).
 *
 * Data is sourced from the same `trend` array used by the main history chart
 * (each entry exposes `dimensionDetails: [{ dimension, score }]`), so no new
 * backend call is required.
 */
import { scoreGradeColorVar } from '../utils/formatters.js';

const MAX_SCORE = 10;
// Visible scores typically hover in the 6–10 range, so mapping 0–10 onto the
// bar height compresses all bars near the top. Clipping the visible range
// restores height contrast without distorting the colour (which still maps
// off the raw score via `scoreGradeColorVar`).
const VISIBLE_MIN_SCORE = 4;

/**
 * Responsive sparkline. The SVG fills 100% of its container width and uses
 * `preserveAspectRatio="none"` so the bars stretch horizontally — the caller
 * controls the final width via CSS on the wrapping element (`.dim-score-spark`).
 *
 * The viewBox is built from a fixed virtual coordinate space so bar/gap
 * proportions stay consistent regardless of rendered width.
 *
 * @param {object} props
 * @param {number[]} props.scores - Oldest-first scores.
 * @param {number} [props.height=20] - Rendered height in px (kept fixed so
 *   rows stay tidy; only the horizontal extent flexes).
 * @param {number} [props.barGapUnits=1] - Gap between bars in viewBox units.
 * @param {number} [props.barUnits=8] - Bar width in viewBox units.
 * @param {number} [props.minHeightRatio=0.18]
 */
export default function DimensionSparkline({
  scores,
  height = 20,
  barGapUnits = 2,
  barUnits = 4,
  minHeightRatio = 0.22,
}) {
  if (!scores || scores.length === 0) {
    return <span className="dim-sparkline dim-sparkline--empty" aria-hidden="true" />;
  }
  const n = scores.length;
  const vbWidth = n * barUnits + (n - 1) * barGapUnits;
  const vbHeight = height;
  const minH = Math.max(1, minHeightRatio * vbHeight);
  const visibleSpan = MAX_SCORE - VISIBLE_MIN_SCORE;
  return (
    <svg
      className="dim-sparkline"
      width="100%"
      height={height}
      viewBox={`0 0 ${vbWidth} ${vbHeight}`}
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      {scores.map((score, i) => {
        // Height uses a clipped 4–10 range so trends are visible; colour
        // still uses the raw score so a 9.8 reads "grade-top" even when the
        // bar is near max height.
        const clipped = Math.max(VISIBLE_MIN_SCORE, Math.min(MAX_SCORE, score));
        const ratio = (clipped - VISIBLE_MIN_SCORE) / visibleSpan;
        const h = Math.max(minH, ratio * vbHeight);
        const x = i * (barUnits + barGapUnits);
        const y = vbHeight - h;
        return (
          <rect
            key={i}
            x={x}
            y={y}
            width={barUnits}
            height={h}
            fill={scoreGradeColorVar(score)}
          />
        );
      })}
    </svg>
  );
}
