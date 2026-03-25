import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreGradeColorVar } from '../../../utils/formatters.js';

function DimensionRow({ dim, onBarClick }) {
  const curr = parseFloat(dim.overallScore);
  const prev = parseFloat(dim.previousScore);
  const delta = !isNaN(curr) && !isNaN(prev) ? curr - prev : null;
  const score = isNaN(curr) ? 0 : curr;
  const pct = Math.min(score / 10, 1) * 100;
  const color = scoreGradeColorVar(score);

  return (
    <div
      className="dim-score-row"
      onClick={() => onBarClick?.(dim)}
      role={onBarClick ? 'button' : undefined}
      tabIndex={onBarClick ? 0 : undefined}
      onKeyDown={onBarClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onBarClick(dim); } } : undefined}
    >
      <span className="dim-score-label">{dim.dimension}</span>
      <div className="dim-score-track">
        <div className="dim-score-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="dim-score-value">{score.toFixed(1)}</span>
      <span className="dim-score-trend"><TrendBadge delta={delta} /></span>
    </div>
  );
}

export default function DimensionScorePanel({ dimensions = [], onBarClick }) {
  if (!dimensions || dimensions.length === 0) return null;

  const sorted = [...dimensions].sort((a, b) => a.dimension.localeCompare(b.dimension));

  return (
    <section className="dim-score-panel panel" aria-label="Dimension scores">
      <div className="run-history-header">
        <span className="run-history-title">Dimension Scores</span>
      </div>
      <div className="dim-score-rows">
        {sorted.map((dim) => (
          <DimensionRow key={dim.dimension} dim={dim} onBarClick={onBarClick} />
        ))}
      </div>
    </section>
  );
}
