const SEVERITY_LEVELS = ['critical', 'major', 'minor'];
const SEVERITY_LABELS = { critical: 'Critical', major: 'Major', minor: 'Minor' };

/**
 * Reusable severity filter pill group.
 * @param {{ counts: { critical: number, major: number, minor: number }, activeFilter: string|null, onFilterChange: function }} props
 */
export default function SeverityFilterPills({ counts, activeFilter, onFilterChange }) {
  const isAllActive = !activeFilter || activeFilter === 'all';
  return (
    <div className="map-pill-group" style={{ justifyContent: 'flex-start' }}>
      <button type="button" className={`map-pill${isAllActive ? ' active' : ''}`} onClick={() => onFilterChange(null)}>
        All
      </button>
      {SEVERITY_LEVELS.map((sev) =>
        counts[sev] > 0 && (
          <button
            key={sev}
            type="button"
            className={`map-pill${activeFilter === sev ? ' active' : ''}`}
            style={{ color: `var(--color-sev-${sev}-text)` }}
            onClick={() => onFilterChange(activeFilter === sev ? null : sev)}
          >
            {SEVERITY_LABELS[sev]} ({counts[sev]})
          </button>
        )
      )}
    </div>
  );
}
