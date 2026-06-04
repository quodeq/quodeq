/**
 * DimensionGaugeCard — large terminal-styled card showing a single dimension's
 * score, grade word, violation/ratio line and severity pills. Shared by the
 * accumulated and run overviews.
 */
import TrendBadge from '../../../components/TrendBadge.jsx';
import { SevBadge } from '../../../components/terminal/index.js';
import { splitScore, scoreGradeColorVar, complianceRatio, formatRunId } from '../../../utils/formatters.js';
import { dimensionGradeLabel } from './dimensionGradeLabel.js';

/**
 * Build a coverage record for the gauge card's footer line.
 *
 * Every card with a date gets a footer line; `coveragePct` and `isPartial`
 * are derived from the same signals as the old partial badge:
 *   - "partial" when filesRead < sourceFileCount, OR
 *   - "partial" when exitReason is set to anything other than 'done'.
 * Legacy runs with neither signal end up complete-by-default.
 *
 * `coveragePct` is null when there are no file counts (legacy runs);
 * in that case the footer renders the date only.
 */
function computeCoverageInfo(filesRead, sourceFileCount, exitReason) {
  const hasCounts =
    typeof filesRead === 'number' &&
    typeof sourceFileCount === 'number' &&
    sourceFileCount > 0;
  const coveragePct = hasCounts
    ? Math.round((filesRead / sourceFileCount) * 100)
    : null;
  const coverageIncomplete = hasCounts && filesRead < sourceFileCount;
  const exitIncomplete = typeof exitReason === 'string' && exitReason !== 'done';
  const isPartial = coverageIncomplete || exitIncomplete;
  return { filesRead, sourceFileCount, coveragePct, exitReason, isPartial };
}

function buildPartialTooltip({ filesRead, sourceFileCount, exitReason }) {
  const hasCounts =
    typeof filesRead === 'number' &&
    typeof sourceFileCount === 'number' &&
    sourceFileCount > 0;
  const parts = ['Partial run'];
  if (hasCounts) {
    parts.push(`${filesRead.toLocaleString()} of ${sourceFileCount.toLocaleString()} files`);
  }
  if (typeof exitReason === 'string') {
    parts.push(`stopped: ${exitReason}`);
  }
  return parts.join(' · ');
}

function CoverageLine({ dateText, coveragePct, isPartial, tooltip }) {
  if (!dateText) return null;
  if (coveragePct === null) {
    return (
      <div className="dim-gauge-card__coverage-line" title={isPartial ? tooltip : undefined}>
        {dateText}
      </div>
    );
  }
  return (
    <div className="dim-gauge-card__coverage-line" title={isPartial ? tooltip : undefined}>
      {dateText} · <span
        className={`dim-gauge-card__coverage-pct${isPartial ? ' dim-gauge-card__coverage-pct--partial' : ''}`}
      >{coveragePct}%</span>
    </div>
  );
}

// SVG geometry — tuned to look right inside the card without scaling JS.
const RING_SIZE = 100;
const RING_STROKE = 8;
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2;
const RING_CIRC = 2 * Math.PI * RING_RADIUS;
const RING_CX = RING_SIZE / 2;
const RING_CY = RING_SIZE / 2;

function handleKey(e, onActivate) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    onActivate();
  }
}

/**
 * @param {object}   props
 * @param {object}   props.item                - dimension entry (dashboard shape)
 * @param {number|string|null} [props.delta]   - trend delta (parent-provided)
 * @param {(item: object) => void} props.onDimensionClick
 * @param {boolean}  [props.evaluatedToday=true] - accumulated overview only: mutes the frame when false
 * @param {string}   [props.dateLabel]         - forwarded to children for run overview
 * @param {string}   [props.selectedRunId]     - forwarded to click handler for run overview
 */
export default function DimensionGaugeCard({
  item,
  delta = null,
  onDimensionClick,
  evaluatedToday = true,
  dateLabel,
  selectedRunId,
  isInsufficient = false,
}) {
  const { value: scoreDisplay } = splitScore(item.overallScore);
  const scoreNum = parseFloat(item.overallScore);
  const hasScore = !Number.isNaN(scoreNum);
  const pct = hasScore ? Math.max(0, Math.min(scoreNum / 10, 1)) : 0;
  const gradeWord = hasScore ? dimensionGradeLabel(scoreNum) : null;
  const ringColor = hasScore ? scoreGradeColorVar(scoreNum) : 'var(--color-text-muted)';
  const dashOffset = RING_CIRC * (1 - pct);

  const violationCount = item.totals?.violationCount ?? 0;
  const complianceCount = item.totals?.complianceCount ?? 0;
  const ratio = complianceRatio(violationCount, complianceCount);
  const sev = item.totals?.severity || {};

  const activate = () => onDimensionClick?.(item, selectedRunId);
  const staleClass = evaluatedToday ? '' : 'dim-gauge-card--stale';
  const dateText = item.fromDateLabel || dateLabel || formatRunId(item.fromRunId || selectedRunId);
  const coverage = computeCoverageInfo(item.filesRead, item.sourceFileCount, item.exitReason);
  const partialTooltip = coverage.isPartial ? buildPartialTooltip(coverage) : undefined;

  return (
    <article
      className={`dim-gauge-card ${staleClass}`.trim()}
      role="button"
      tabIndex={0}
      onClick={activate}
      onKeyDown={(e) => handleKey(e, activate)}
      aria-label={`${item.dimension} dimension details`}
    >
      <div className="dim-gauge-card__head">
        <span className="dim-gauge-card__name">{item.dimension}</span>
        {delta !== null && delta !== undefined && <TrendBadge delta={delta} />}
      </div>

      {isInsufficient ? (
        <>
          <div className="dim-gauge-card__gauge dim-gauge-card__gauge--insuf" aria-hidden="true">
            <svg width={RING_SIZE} height={RING_SIZE} viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}>
              <circle
                className="dim-gauge-card__ring-bg"
                cx={RING_CX} cy={RING_CY} r={RING_RADIUS}
                strokeWidth={RING_STROKE}
                strokeDasharray="3 4"
              />
              <text className="dim-gauge-card__score" x={RING_CX} y={RING_CY - 4}>—</text>
              <text className="dim-gauge-card__grade" x={RING_CX} y={RING_CY + 16}>INSUFFICIENT</text>
            </svg>
          </div>
          <div className="dim-gauge-card__insuf-line">insufficient evidence</div>
        </>
      ) : (
        <>
          <div className="dim-gauge-card__gauge" aria-hidden="true">
            <svg width={RING_SIZE} height={RING_SIZE} viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}>
              <circle
                className="dim-gauge-card__ring-bg"
                cx={RING_CX} cy={RING_CY} r={RING_RADIUS}
                strokeWidth={RING_STROKE}
              />
              <circle
                className="dim-gauge-card__ring-fill"
                cx={RING_CX} cy={RING_CY} r={RING_RADIUS}
                strokeWidth={RING_STROKE}
                stroke={ringColor}
                strokeDasharray={RING_CIRC}
                strokeDashoffset={dashOffset}
                transform={`rotate(-90 ${RING_CX} ${RING_CY})`}
              />
              <text className="dim-gauge-card__score" x={RING_CX} y={RING_CY - 4}>
                {scoreDisplay}
              </text>
              {gradeWord && (
                <text className="dim-gauge-card__grade" x={RING_CX} y={RING_CY + 16}>
                  {gradeWord}
                </text>
              )}
            </svg>
          </div>

          <div className="dim-gauge-card__meta">
            VIOL · {violationCount} · {ratio}
          </div>

          <div className="dim-gauge-card__sev-row">
            {(sev.critical ?? 0) > 0 && <SevBadge level="critical" count={sev.critical} format="count-abbr" />}
            {(sev.major ?? 0)    > 0 && <SevBadge level="major"    count={sev.major}    format="count-abbr" />}
            {(sev.minor ?? 0)    > 0 && <SevBadge level="minor"    count={sev.minor}    format="count-abbr" />}
          </div>
        </>
      )}

      <CoverageLine
        dateText={dateText}
        coveragePct={coverage.coveragePct}
        isPartial={coverage.isPartial}
        tooltip={partialTooltip}
      />
    </article>
  );
}
