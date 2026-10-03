import { SevBadge } from '../../../components/terminal/index.js';
import { SEVERITY } from '../../../vocab/severity.js';

// A chip shows when it has a count, or when its count dropped to zero since
// the baseline: "0 crit ▾3" is the news, so the zero keeps its chip.
function shows(sev, deltas, level) {
  return sev[level] > 0 || Boolean(deltas?.[level]);
}

// Shared by AccumulatedHeroSection and RunHeroSection -- byte-identical
// markup/behavior in both, deduped into one component. `deltas` (from
// chipDeltas) puts the change since the baseline run on the critical and
// major chips; without it the chips read as plain counts.
export default function SeverityBadgeRow({ severity, onSeverityClick, deltas = null }) {
  const sev = severity || {};
  const levels = [SEVERITY.CRITICAL, SEVERITY.MAJOR, SEVERITY.MINOR].filter((level) => shows(sev, deltas, level));
  if (levels.length === 0) return null;
  return (
    <span className="acc-eval-sev-row">
      {levels.map((level) => (
        <SevBadge
          key={level}
          level={level}
          count={sev[level] || 0}
          delta={deltas?.[level]}
          format="count-abbr"
          onClick={onSeverityClick ? () => onSeverityClick(level) : undefined}
        />
      ))}
    </span>
  );
}
