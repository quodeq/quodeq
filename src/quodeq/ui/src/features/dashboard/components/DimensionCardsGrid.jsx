import TrendBadge from '../../../components/TrendBadge.jsx';
import { formatRunId, gradeColorClass, splitScore } from '../../../utils/formatters.js';

export default function DimensionCardsGrid({ sortedDimensions, referenceRun, onDimensionClick }) {
  return (
    <div className="dimensions-grid">
      {sortedDimensions.map((item) => {
          const isStale = item.fromRunId !== referenceRun;
          const currScore = parseFloat(item.overallScore);
          const prevScore = parseFloat(item.previousScore);
          const delta =
            !isNaN(currScore) && !isNaN(prevScore) ? currScore - prevScore : null;
          const score = splitScore(item.overallScore);
          return (
            <article
              key={item.dimension}
              className={`qd-card${isStale ? ' qd-card-stale' : ''}`}
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
                  {score.denom && (
                    <span className="qd-card-score-denom">
                      {score.denom}
                    </span>
                  )}
                </span>
                <TrendBadge delta={delta} />
              </div>
              <div className="qd-card-stats">
                {(item.totals?.violationCount ?? 0) > 0 && (
                  <span className="qd-card-stat-violations">
                    {item.totals.violationCount} violations
                  </span>
                )}
                {(item.totals?.complianceCount ?? 0) > 0 && (
                  <span className="qd-card-stat-compliance">
                    {item.totals.complianceCount} compliant
                  </span>
                )}
              </div>
              <div className="qd-card-footer">
                <span className="qd-card-date">{item.fromDateLabel || formatRunId(item.fromRunId)}</span>
                {isStale && <span className="qd-card-stale-label">Older run</span>}
              </div>
            </article>
          );
        })}
    </div>
  );
}
