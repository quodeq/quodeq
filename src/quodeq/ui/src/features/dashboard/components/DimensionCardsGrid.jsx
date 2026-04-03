import { useMemo } from 'react';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { formatRunId, scoreColorClass, splitScore, complianceRatio } from '../../../utils/formatters.js';

function AccDimensionCard({ item, onDimensionClick, evaluatedToday = true, rescoreLookup }) {
  const match = rescoreLookup?.[(item.dimension || '').toLowerCase()];
  const effectiveItem = match ? { ...item, overallScore: match.overallScore, overallGrade: match.overallGrade, totals: match.totals ?? item.totals } : item;
  const currScore = parseFloat(effectiveItem.overallScore);
  const prevScore = parseFloat(effectiveItem.previousScore);
  const delta = !isNaN(currScore) && !isNaN(prevScore) ? currScore - prevScore : null;
  const score = splitScore(effectiveItem.overallScore);
  const gradeClass = scoreColorClass(currScore);
  const staleClass = evaluatedToday ? 'qd-card--active' : 'qd-card-stale qd-card--carried';
  return (
    <article
      className={`qd-card ${staleClass} ${gradeClass}`}
      onClick={() => onDimensionClick(effectiveItem)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onDimensionClick(item); } }}
    >
      <div className="qd-card-header">
        <div className="qd-card-name-row">
          {evaluatedToday && <span className="qd-card-dot" />}
          <span className="qd-card-name">{item.dimension}</span>
        </div>
        <TrendBadge delta={delta} />
      </div>
      <div className="qd-card-columns">
        <div className="qd-card-col">
          <span className="qd-card-col-score">{score.value}</span>
        </div>
        <div className="qd-card-col-divider" />
        <div className="qd-card-col">
          <span className="qd-card-col-label">Viol</span>
          <span className="qd-card-col-value">{effectiveItem.totals?.violationCount ?? 0}</span>
        </div>
        <div className="qd-card-col-divider" />
        <div className="qd-card-col">
          <span className="qd-card-col-label">Ratio</span>
          <span className="qd-card-col-value">{complianceRatio(effectiveItem.totals?.violationCount ?? 0, effectiveItem.totals?.complianceCount ?? 0)}</span>
        </div>
      </div>
      <div className="qd-card-footer">
        <span className="qd-card-date">{item.fromDateLabel || formatRunId(item.fromRunId)}</span>
        {!evaluatedToday && <span className="qd-card-stale-label">Older run</span>}
      </div>
      <div className="qd-card-grade-bar" />
    </article>
  );
}

export default function DimensionCardsGrid({ sortedDimensions, onDimensionClick, selectedDayDimNames, rescoreLookup }) {
  const dimNameSet = selectedDayDimNames instanceof Set ? selectedDayDimNames : new Set();
  const sorted = useMemo(() => [...sortedDimensions].sort((a, b) => {
    if (dimNameSet.size === 0) return a.dimension.localeCompare(b.dimension);
    const aActive = dimNameSet.has((a.dimension || '').toLowerCase());
    const bActive = dimNameSet.has((b.dimension || '').toLowerCase());
    if (aActive && !bActive) return -1;
    if (!aActive && bActive) return 1;
    return a.dimension.localeCompare(b.dimension);
  }), [sortedDimensions, dimNameSet]);
  return (
    <div className="dimensions-grid">
      {sorted.map((item) => {
        const isActive = dimNameSet.size === 0 || dimNameSet.has((item.dimension || '').toLowerCase());
        return (
          <AccDimensionCard
            key={item.dimension}
            item={item}
            onDimensionClick={onDimensionClick}
            evaluatedToday={isActive}
            rescoreLookup={rescoreLookup}
          />
        );
      })}
    </div>
  );
}
