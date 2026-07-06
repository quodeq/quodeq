import TrendBadge from '../../../components/TrendBadge.jsx';
import DimensionSparkline from '../../../components/DimensionSparkline.jsx';

function violationCount(dim) {
  if (typeof dim.totalViolations === 'number') return dim.totalViolations;
  if (Array.isArray(dim.violations)) return dim.violations.length;
  return 0;
}

function DimensionRow({ dim, onBarClick, delta, scores }) {
  const curr = parseFloat(dim.overallScore);
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
        <DimensionSparkline scores={scores} />
      </span>
      <span className="dim-score-value">{score.toFixed(1)}</span>
      <span className="dim-score-trend"><TrendBadge delta={delta} /></span>
      <span className="dim-score-viol">{violations}v</span>
    </div>
  );
}

// Fallback delta when the parent did not supply a period-aware entry for this
// dimension (defensive; the accumulated overview always supplies dimTrends).
function fallbackDelta(dim) {
  const curr = parseFloat(dim.overallScore);
  const prev = parseFloat(dim.previousScore);
  return !Number.isNaN(curr) && !Number.isNaN(prev) ? curr - prev : null;
}

export default function DimensionScorePanel({ dimensions = [], onBarClick, dimTrends }) {
  if (!dimensions || dimensions.length === 0) return null;

  const sorted = [...dimensions].sort((a, b) => a.dimension.localeCompare(b.dimension));

  return (
    <section className="dim-score-panel dim-score-panel--terminal panel" aria-label="Dimension scores">
      <header className="dim-score-panel__header">DIMENSIONS</header>
      <div className="dim-score-rows">
        {sorted.map((dim) => {
          const entry = dimTrends?.[(dim.dimension || '').toLowerCase()];
          const delta = entry ? entry.delta : fallbackDelta(dim);
          const scores = entry ? entry.scores : [];
          return (
            <DimensionRow
              key={dim.dimension}
              dim={dim}
              onBarClick={onBarClick}
              delta={delta}
              scores={scores}
            />
          );
        })}
      </div>
    </section>
  );
}
