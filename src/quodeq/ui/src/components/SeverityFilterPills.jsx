import FlagPill from './terminal/FlagPill.jsx';

const SEVERITY_LEVELS = ['critical', 'major', 'minor'];

/**
 * Reusable severity filter pill group rendered in the terminal `--flag` style.
 * Each severity-coloured pill picks up its accent from `--color-sev-<level>-text`.
 * When `complianceCount` is passed, an extra `--compliance` pill is rendered
 * alongside the severity pills.
 *
 * @param {{
 *   counts: { critical: number, major: number, minor: number },
 *   complianceCount?: number,
 *   activeFilter: string|null,
 *   onFilterChange: (filter: string|null) => void,
 * }} props
 */
export default function SeverityFilterPills({ counts, complianceCount = 0, activeFilter, onFilterChange }) {
  const isAllActive = !activeFilter || activeFilter === 'all';
  const toggle = (key) => onFilterChange(activeFilter === key ? null : key);
  return (
    <div className="term-flag-row">
      <FlagPill flag="all" active={isAllActive} onClick={() => onFilterChange(null)} />
      {SEVERITY_LEVELS.map((sev) =>
        counts[sev] > 0 ? (
          <FlagPill
            key={sev}
            flag={sev}
            tone={sev}
            count={counts[sev]}
            active={activeFilter === sev}
            onClick={() => toggle(sev)}
          />
        ) : null
      )}
      {complianceCount > 0 && (
        <FlagPill
          flag="compliance"
          count={complianceCount}
          active={activeFilter === 'compliance'}
          onClick={() => toggle('compliance')}
        />
      )}
    </div>
  );
}
