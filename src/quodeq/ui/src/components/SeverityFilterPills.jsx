import FlagPill from './terminal/FlagPill.jsx';

const SEVERITY_LEVELS = ['critical', 'major', 'minor'];
const SEVERITY_FLAGS = { critical: 'critical', major: 'major', minor: 'minor' };

/**
 * Reusable severity filter pill group rendered in the terminal `--flag` style.
 * Each severity-coloured pill picks up its accent from `--color-sev-<level>-text`.
 * @param {{ counts: { critical: number, major: number, minor: number }, activeFilter: string|null, onFilterChange: function }} props
 */
export default function SeverityFilterPills({ counts, activeFilter, onFilterChange }) {
  const isAllActive = !activeFilter || activeFilter === 'all';
  return (
    <div className="term-flag-row">
      <FlagPill flag="all" active={isAllActive} onClick={() => onFilterChange(null)} />
      {SEVERITY_LEVELS.map((sev) =>
        counts[sev] > 0 ? (
          <span
            key={sev}
            className={`term-flag-sev term-flag-sev--${sev}`}
            style={{ '--term-sev-accent': `var(--color-sev-${sev}-text)` }}
          >
            <FlagPill
              flag={SEVERITY_FLAGS[sev]}
              count={counts[sev]}
              active={activeFilter === sev}
              onClick={() => onFilterChange(activeFilter === sev ? null : sev)}
            />
          </span>
        ) : null
      )}
    </div>
  );
}
