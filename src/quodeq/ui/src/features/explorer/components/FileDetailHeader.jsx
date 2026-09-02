import { TermHeader, StatStrip, Stat, SevBadge } from '../../../components/terminal/index.js';
import { complianceRatio } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';

function FileSevBadgeRow({ sevCounts }) {
  if (!(sevCounts.critical || sevCounts.major || sevCounts.minor)) return null;
  return (
    <span className="principle-detail-sev-row">
      {sevCounts.critical > 0 && <SevBadge level="critical" count={sevCounts.critical} format="count-abbr" />}
      {sevCounts.major    > 0 && <SevBadge level="major"    count={sevCounts.major}    format="count-abbr" />}
      {sevCounts.minor    > 0 && <SevBadge level="minor"    count={sevCounts.minor}    format="count-abbr" />}
    </span>
  );
}

export default function FileDetailHeader({ file, sevCounts, totalViolations, totalCompliance, dimensionsCount, dateLabel, runId }) {
  const totalChecks = totalViolations + totalCompliance;
  const ratio = complianceRatio(totalViolations, totalCompliance);
  return (
    <section className="principle-detail-header principle-detail-header--terminal">
      <div className="principle-detail-header__top">
        <TermHeader name={file.file} sub={dateLabel || runId || null} />
      </div>
      <StatStrip cards>
        <Stat
          label={t('overview.statViolations')}
          value={totalViolations}
          hint={<FileSevBadgeRow sevCounts={sevCounts} />}
        />
        <Stat
          label={t('overview.statCompliance')}
          value={totalCompliance}
          hint={totalChecks > 0 ? t('overview.passingChecks', { count: totalChecks }) : null}
        />
        <Stat
          label={t('overview.statRatio')}
          value={ratio}
          hint={t('overview.ratioHint')}
        />
        <Stat
          label={t('explorer.dimensionsStat')}
          value={dimensionsCount}
        />
      </StatStrip>
    </section>
  );
}
