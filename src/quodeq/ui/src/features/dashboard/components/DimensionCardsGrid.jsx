import TrendBadge from '../../../components/TrendBadge.jsx';
import { formatRunId, gradeColorClass, splitScore } from '../../../utils/formatters.js';

function AccDimensionCard({ item, referenceRun, onDimensionClick, evaluatedToday = true }) {
  const isStale = item.fromRunId !== referenceRun;
  const currScore = parseFloat(item.overallScore);
  const prevScore = parseFloat(item.previousScore);
  const delta = !isNaN(currScore) && !isNaN(prevScore) ? currScore - prevScore : null;
  const score = splitScore(item.overallScore);
  const cardClass = `qd-card${isStale ? ' qd-card-stale' : ''}${evaluatedToday ? ' qd-card--active' : ' qd-card--carried'}`;
  return (
    <article
      className={cardClass}
      onClick={() => onDimensionClick(item)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onDimensionClick(item); } }}
    >
      <div className="qd-card-header">
        <span className="qd-card-name">{item.dimension}</span>
        <span className={`chip small ${gradeColorClass(item.overallGrade)}`}>
          {item.overallGrade || '—'}
        </span>
      </div>
      <div className="qd-card-score-row">
        <span className="qd-card-score-main">
          <span className="qd-card-score">{score.value}</span>
          {score.denom && <span className="qd-card-score-denom">{score.denom}</span>}
        </span>
        {evaluatedToday && <TrendBadge delta={delta} />}
      </div>
      <div className="qd-card-stats">
        {(item.totals?.violationCount ?? 0) > 0 && (
          <span className="qd-card-stat-violations">{item.totals.violationCount} violations</span>
        )}
        {(item.totals?.complianceCount ?? 0) > 0 && (
          <span className="qd-card-stat-compliance">{item.totals.complianceCount} compliant</span>
        )}
      </div>
      <div className="qd-card-footer">
        <span className="qd-card-date">{item.fromDateLabel || formatRunId(item.fromRunId)}</span>
        {isStale && <span className="qd-card-stale-label">Older run</span>}
      </div>
    </article>
  );
}

export default function DimensionCardsGrid({ sortedDimensions, referenceRun, onDimensionClick, selectedDayDate }) {
  // Each dimension has fromDateISO — compare its date to the selected day
  const sorted = [...sortedDimensions].sort((a, b) => {
    if (!selectedDayDate) return a.dimension.localeCompare(b.dimension);
    const aDate = (a.fromDateISO || '').slice(0, 10);
    const bDate = (b.fromDateISO || '').slice(0, 10);
    const aActive = aDate === selectedDayDate;
    const bActive = bDate === selectedDayDate;
    if (aActive && !bActive) return -1;
    if (!aActive && bActive) return 1;
    return a.dimension.localeCompare(b.dimension);
  });
  return (
    <div className="dimensions-grid">
      {sorted.map((item) => {
        const dimDate = (item.fromDateISO || '').slice(0, 10);
        const isActive = !selectedDayDate || dimDate === selectedDayDate;
        return (
          <AccDimensionCard
            key={item.dimension}
            item={item}
            referenceRun={referenceRun}
            onDimensionClick={onDimensionClick}
            evaluatedToday={isActive}
          />
        );
      })}
    </div>
  );
}
