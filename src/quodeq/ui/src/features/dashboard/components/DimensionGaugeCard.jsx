/**
 * DimensionGaugeCard — large terminal-styled card showing a single dimension's
 * score, grade word, violation/ratio line and severity pills. Shared by the
 * accumulated and run overviews.
 */
import { useId } from 'react';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { SevBadge } from '../../../components/terminal/index.js';
import { splitScore, scoreGradeColorVar, complianceRatio, formatRunId } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';
import { computeCoverageInfo, buildPartialTooltip } from './dimensionGaugeMath.js';
import { activateOnKey } from '../../../utils/a11y.js';
import { SCORE_SCALE_MAX } from '../../../constants.js';

/**
 * Findings the scan produced but scoring never saw, because the principle they
 * named is not in this dimension's standard. Not a findings bucket: they have no
 * principle, so no card and no score. The count sits next to coverage because it
 * answers the same question, how much of the evidence actually reached the grade.
 *
 * Renders nothing at 0, which is every healthy run and every report written
 * before the field existed.
 */
function UnmappedSegment({ count }) {
  if (!count) return null;
  const tooltipKey = count === 1 ? 'overview.unmappedTooltipOne' : 'overview.unmappedTooltipMany';
  return (
    <> · <span
      className="dim-gauge-card__unmapped"
      title={t(tooltipKey, { count: count.toLocaleString(LOCALE) })}
    >{t('overview.unmappedCount', { count: count.toLocaleString(LOCALE) })}</span></>
  );
}

function CoverageLine({ dateText, coveragePct, isPartial, tooltip, quarantinedCount }) {
  if (!dateText) return null;
  return (
    <div className="dim-gauge-card__coverage-line" title={isPartial ? tooltip : undefined}>
      {dateText}
      {coveragePct !== null && (
        <> · <span
          className={`dim-gauge-card__coverage-pct${isPartial ? ' dim-gauge-card__coverage-pct--partial' : ''}`}
        >{coveragePct}%</span></>
      )}
      <UnmappedSegment count={quarantinedCount} />
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
// Text baseline offsets from ring center: score sits just above, grade word
// just below.
const SCORE_TEXT_OFFSET_Y = 4;
const GRADE_TEXT_OFFSET_Y = 16;

function InsufficientGauge() {
  return (
    <>
      <div className="dim-gauge-card__gauge dim-gauge-card__gauge--insuf" aria-hidden="true">
        <svg width={RING_SIZE} height={RING_SIZE} viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}>
          <circle
            className="dim-gauge-card__ring-bg"
            cx={RING_CX} cy={RING_CY} r={RING_RADIUS}
            strokeWidth={RING_STROKE}
            strokeDasharray="3 4"
          />
          <text className="dim-gauge-card__score" x={RING_CX} y={RING_CY - SCORE_TEXT_OFFSET_Y}>—</text>
          <text className="dim-gauge-card__grade" x={RING_CX} y={RING_CY + GRADE_TEXT_OFFSET_Y}>{t('overview.insufficientGrade')}</text>
        </svg>
      </div>
      <div className="dim-gauge-card__insuf-line">{t('overview.insufficientEvidence')}</div>
    </>
  );
}

function ScoreGauge({ scoreDisplay, gradeWord, ringColor, dashOffset }) {
  return (
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
        <text className="dim-gauge-card__score" x={RING_CX} y={RING_CY - SCORE_TEXT_OFFSET_Y}>
          {scoreDisplay}
        </text>
        {gradeWord && (
          <text className="dim-gauge-card__grade" x={RING_CX} y={RING_CY + GRADE_TEXT_OFFSET_Y}>
            {gradeWord}
          </text>
        )}
      </svg>
    </div>
  );
}

function DimensionScoreBody({ scoreDisplay, gradeWord, ringColor, dashOffset, violationCount, ratio, sev, summaryId }) {
  return (
    <>
      <ScoreGauge scoreDisplay={scoreDisplay} gradeWord={gradeWord} ringColor={ringColor} dashOffset={dashOffset} />
      <span id={summaryId} className="sr-only">{t('overview.gaugeSummaryAria', { score: scoreDisplay, grade: gradeWord })}</span>

      <div className="dim-gauge-card__meta">
        {t('overview.violAbbrev')} · {violationCount} · {ratio}
      </div>

      <div className="dim-gauge-card__sev-row">
        {(sev.critical ?? 0) > 0 && <SevBadge level="critical" count={sev.critical} format="count-abbr" />}
        {(sev.major ?? 0)    > 0 && <SevBadge level="major"    count={sev.major}    format="count-abbr" />}
        {(sev.minor ?? 0)    > 0 && <SevBadge level="minor"    count={sev.minor}    format="count-abbr" />}
      </div>
    </>
  );
}

/**
 * Ring geometry and colour for one dimension's score. A dimension with no
 * parsable score draws an empty muted ring and no grade word.
 */
function computeGaugeRing(overallScore) {
  const { value: scoreDisplay } = splitScore(overallScore);
  const scoreNum = parseFloat(overallScore);
  const hasScore = !Number.isNaN(scoreNum);
  const pct = hasScore ? Math.max(0, Math.min(scoreNum / SCORE_SCALE_MAX, 1)) : 0;
  const label = hasScore ? scoreToGradeLabel(scoreNum) : null;
  return {
    scoreDisplay,
    gradeWord: label ? label.toUpperCase() : null,
    ringColor: hasScore ? scoreGradeColorVar(scoreNum) : 'var(--color-text-muted)',
    dashOffset: RING_CIRC * (1 - pct),
  };
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
function computeGaugeCardDerived({ item, evaluatedToday, dateLabel, selectedRunId }) {
  const violationCount = item.totals?.violationCount ?? 0;
  const complianceCount = item.totals?.complianceCount ?? 0;
  const coverage = computeCoverageInfo(item.filesRead, item.sourceFileCount, item.exitReason);

  return {
    ...computeGaugeRing(item.overallScore),
    violationCount,
    ratio: complianceRatio(violationCount, complianceCount),
    sev: item.totals?.severity || {},
    staleClass: evaluatedToday ? '' : 'dim-gauge-card--stale',
    dateText: item.fromDateLabel || dateLabel || formatRunId(item.fromRunId || selectedRunId),
    coverage,
    partialTooltip: coverage.isPartial ? buildPartialTooltip(coverage) : undefined,
  };
}

export default function DimensionGaugeCard({
  item,
  delta = null,
  onDimensionClick,
  evaluatedToday = true,
  dateLabel,
  selectedRunId,
  isInsufficient = false,
}) {
  const {
    scoreDisplay, gradeWord, ringColor, dashOffset, violationCount, ratio, sev,
    staleClass, dateText, coverage, partialTooltip,
  } = computeGaugeCardDerived({ item, evaluatedToday, dateLabel, selectedRunId });
  const activate = () => onDimensionClick?.(item, selectedRunId);
  // role="button" gives the article children-presentational semantics, and the
  // explicit aria-label above already skips its content -- so the sr-only score
  // summary needs its own id wired up via aria-describedby to reach assistive
  // tech at all. No description when insufficient:
  // InsufficientGauge's own caption isn't aria-hidden, so it's already exposed.
  const summaryId = useId();

  return (
    <article
      className={`dim-gauge-card ${staleClass}`.trim()}
      role="button"
      tabIndex={0}
      onClick={activate}
      onKeyDown={activateOnKey(activate)}
      aria-label={t('overview.dimensionDetailsAria', { name: item.dimension })}
      aria-describedby={isInsufficient ? undefined : summaryId}
    >
      <div className="dim-gauge-card__head">
        <span className="dim-gauge-card__name">{item.dimension}</span>
        {delta !== null && delta !== undefined && <TrendBadge delta={delta} />}
      </div>

      {isInsufficient ? (
        <InsufficientGauge />
      ) : (
        <DimensionScoreBody
          scoreDisplay={scoreDisplay} gradeWord={gradeWord} ringColor={ringColor} dashOffset={dashOffset}
          violationCount={violationCount} ratio={ratio} sev={sev}
          summaryId={summaryId}
        />
      )}

      <CoverageLine
        dateText={dateText}
        coveragePct={coverage.coveragePct}
        isPartial={coverage.isPartial}
        tooltip={partialTooltip}
        quarantinedCount={item.quarantinedCount}
      />
    </article>
  );
}
