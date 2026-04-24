import TrendBadge from '../../../components/TrendBadge.jsx';
import DimensionSparkline, { extractDimensionHistory } from '../../../components/DimensionSparkline.jsx';

const SPARKLINE_LIMIT = 10;

function violationCount(dim) {
  if (typeof dim.totalViolations === 'number') return dim.totalViolations;
  if (Array.isArray(dim.violations)) return dim.violations.length;
  return 0;
}

function DimensionRow({ dim, onBarClick, history }) {
  const curr = parseFloat(dim.overallScore);
  const prev = parseFloat(dim.previousScore);
  const delta = !Number.isNaN(curr) && !Number.isNaN(prev) ? curr - prev : null;
  const score = Number.isNaN(curr) ? 0 : curr;
  const violations = violationCount(dim);

  return (
    <div
      className="dim-score-row dim-score-row--terminal"
      onClick={() => onBarClick?.(dim)}
      role={onBarClick ? 'button' : undefined}
      tabIndex={onBarClick ? 0 : undefined}
      onKeyDown={onBarClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onBarClick(dim); } } : undefined}
    >
      <span className="dim-score-label">{String(dim.dimension || '').toLowerCase()}</span>
      <span className="dim-score-spark">
        <DimensionSparkline scores={history} />
      </span>
      <span className="dim-score-value">{score.toFixed(1)}</span>
      <span className="dim-score-trend"><TrendBadge delta={delta} /></span>
      <span className="dim-score-viol">{violations}v</span>
    </div>
  );
}

export default function DimensionScorePanel({ dimensions = [], onBarClick, trend = [] }) {
  if (!dimensions || dimensions.length === 0) return null;

  const sorted = [...dimensions].sort((a, b) => a.dimension.localeCompare(b.dimension));

  return (
    <section className="dim-score-panel dim-score-panel--terminal panel" aria-label="Dimension scores">
      <header className="dim-score-panel__header">DIMENSIONS</header>
      <div className="dim-score-rows">
        {sorted.map((dim) => (
          <DimensionRow
            key={dim.dimension}
            dim={dim}
            onBarClick={onBarClick}
            history={extractDimensionHistory(trend, dim.dimension, SPARKLINE_LIMIT)}
          />
        ))}
      </div>
    </section>
  );
}
