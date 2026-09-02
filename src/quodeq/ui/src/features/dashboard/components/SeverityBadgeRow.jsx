import { SevBadge } from '../../../components/terminal/index.js';

// Shared by AccumulatedHeroSection and RunHeroSection -- byte-identical
// markup/behavior in both, deduped into one component (Task 22).
export default function SeverityBadgeRow({ severity, onSeverityClick }) {
  const sev = severity || {};
  if (!(sev.critical || sev.major || sev.minor)) return null;
  const onClickFor = (level) => onSeverityClick ? () => onSeverityClick(level) : undefined;
  return (
    <span className="acc-eval-sev-row">
      {sev.critical > 0 && <SevBadge level="critical" count={sev.critical} format="count-abbr" onClick={onClickFor('critical')} />}
      {sev.major > 0    && <SevBadge level="major"    count={sev.major}    format="count-abbr" onClick={onClickFor('major')} />}
      {sev.minor > 0    && <SevBadge level="minor"    count={sev.minor}    format="count-abbr" onClick={onClickFor('minor')} />}
    </span>
  );
}
