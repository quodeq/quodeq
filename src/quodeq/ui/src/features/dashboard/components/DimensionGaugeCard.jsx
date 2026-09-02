/**
 * DimensionGaugeCard — large terminal-styled card showing a single dimension's
 * score, grade word, violation/ratio line and severity pills. Shared by the
 * accumulated and run overviews.
 */
import TrendBadge from '../../../components/TrendBadge.jsx';
import { SevBadge } from '../../../components/terminal/index.js';
import { splitScore, scoreGradeColorVar, complianceRatio, formatRunId } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';
import { computeCoverageInfo, buildPartialTooltip } from './dimensionGaugeMath.js';

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

function handleKey(e, onActivate) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    onActivate();
  }
}

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
          <text className="dim-gauge-card__score" x={RING_CX} y={RING_CY - 4}>—</text>
          <text className="dim-gauge-card__grade" x={RING_CX} y={RING_CY + 16}>{t('overview.insufficientGrade')}</text>
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
  );
}

function DimensionScoreBody({ scoreDisplay, gradeWord, ringColor, dashOffset, violationCount, ratio, sev }) {
  return (
    <>
      <ScoreGauge scoreDisplay={scoreDisplay} gradeWord={gradeWord} ringColor={ringColor} dashOffset={dashOffset} />

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
 * @param {object}   props
 * @param {object}   props.item                - dimension entry (dashboard shape)
 * @param {number|string|null} [props.delta]   - trend delta (parent-provided)
 * @param {(item: object) => void} props.onDimensionClick
 * @param {boolean}  [props.evaluatedToday=true] - accumulated overview only: mutes the frame when false
 * @param {string}   [props.dateLabel]         - forwarded to children for run overview
 * @param {string}   [props.selectedRunId]     - forwarded to click handler for run overview
 */
function computeGaugeCardDerived({ item, evaluatedToday, dateLabel, selectedRunId }) {
  const { value: scoreDisplay } = splitScore(item.overallScore);
  const scoreNum = parseFloat(item.overallScore);
  const hasScore = !Number.isNaN(scoreNum);
  const pct = hasScore ? Math.max(0, Math.min(scoreNum / 10, 1)) : 0;
  const label = hasScore ? scoreToGradeLabel(scoreNum) : null;
  const gradeWord = label ? label.toUpperCase() : null;
  const ringColor = hasScore ? scoreGradeColorVar(scoreNum) : 'var(--color-text-muted)';
  const dashOffset = RING_CIRC * (1 - pct);

  const violationCount = item.totals?.violationCount ?? 0;
  const complianceCount = item.totals?.complianceCount ?? 0;
  const ratio = complianceRatio(violationCount, complianceCount);
  const sev = item.totals?.severity || {};

  const staleClass = evaluatedToday ? '' : 'dim-gauge-card--stale';
  const dateText = item.fromDateLabel || dateLabel || formatRunId(item.fromRunId || selectedRunId);
  const coverage = computeCoverageInfo(item.filesRead, item.sourceFileCount, item.exitReason);
  const partialTooltip = coverage.isPartial ? buildPartialTooltip(coverage) : undefined;

  return {
    scoreDisplay, gradeWord, ringColor, dashOffset, violationCount, ratio, sev,
    staleClass, dateText, coverage, partialTooltip,
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

  return (
    <article
      className={`dim-gauge-card ${staleClass}`.trim()}
      role="button"
      tabIndex={0}
      onClick={activate}
      onKeyDown={(e) => handleKey(e, activate)}
      aria-label={t('overview.dimensionDetailsAria', { name: item.dimension })}
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
