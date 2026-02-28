// Props: { dimension, onClick }
// Renders a single row in a violations table for a dimension.
// Shows dimension name, total violation count, and severity breakdown tags.
// onClick is called when the row button is clicked.

export default function DimensionViolationsRow({ dimension, onClick }) {
  const violations = dimension.violations || [];
  if (violations.length === 0) return null;

  const counts = { critical: 0, major: 0, minor: 0 };
  violations.forEach((v) => {
    const sev = (v.severity || 'minor').toLowerCase();
    if (counts[sev] !== undefined) counts[sev]++;
  });
  const total = violations.length;
  const hasTags = counts.critical > 0 || counts.major > 0 || counts.minor > 0;

  return (
    <button className="dimension-violations-row" onClick={onClick}>
      <span className="dimension-name">{dimension.dimension}</span>
      <strong className="offending-file-total">{total}</strong>
      {hasTags && (
        <span className="offending-file-tags">
          {counts.critical > 0 && (
            <span className="severity-tag critical">{counts.critical} critical</span>
          )}
          {counts.major > 0 && (
            <span className="severity-tag major">{counts.major} major</span>
          )}
          {counts.minor > 0 && (
            <span className="severity-tag minor">{counts.minor} minor</span>
          )}
        </span>
      )}
      <span className="row-arrow">›</span>
    </button>
  );
}
