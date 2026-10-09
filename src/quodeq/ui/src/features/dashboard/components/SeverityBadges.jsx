/** The critical / major / minor badges of a count set, zeros left out. */
import { SevBadge, GridCell } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { SEVERITY_ORDER } from '../../../vocab/severity.js';

export default function SeverityBadges({ sev }) {
  return (
    <span className="offending-file-tags">
      {SEVERITY_ORDER.map((level) => (sev?.[level] ?? 0) > 0 && (
        <SevBadge key={level} level={level} count={sev[level]} format="count-abbr" />
      ))}
    </span>
  );
}

/** A grouped row's closing cells: its severity badges, then its file count. */
export function SeverityAndFilesCells({ sev, fileCount }) {
  return (
    <>
      <GridCell><SeverityBadges sev={sev} /></GridCell>
      <GridCell numeric>{t('overview.fileCountAbbrev', { count: fileCount })}</GridCell>
    </>
  );
}
