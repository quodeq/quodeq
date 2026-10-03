import { Stat, SevBadge } from '../../../components/terminal/index.js';
import { formatScoreDisplay } from '../../../utils/gradeFormatting.js';
import StatGrid2x2 from './StatGrid2x2.jsx';
import DimensionScoreHistoryPanel from './DimensionScoreHistoryPanel.jsx';
import { t } from '../../../strings/index.js';
import { SEVERITY_ORDER } from '../../../vocab/severity.js';
import { HERO_CARD_KIND } from '../../dashboard/dashboardVocab.js';
import { RatioDensityStat, ScoreStat, ratioDisplay } from '../../dashboard/components/heroSectionParts.jsx';

/** The score/violations/compliance/ratio stat grid and the run-history bar
 * chart: the left column of the dimension page's top grid. */
export default function ExplorerStatsPanel({
  overallScoreNum, overallGrade, allViolations, totalCompliant, sev, onSeverityBadge,
  onNavigate, onCardNavigate, trend, dimension, activeRunId, granularity, onGranularityChange, onBarClick, deltas = null, density = null,
}) {
  return (
    <div className="qd-top-left">
      <StatGrid2x2>
        <ScoreStat scoreDisplay={formatScoreDisplay(overallScoreNum)} grade={overallGrade?.grade} />
        <Stat
          label={t('overview.statViolations')}
          value={allViolations.length}
          hint={SEVERITY_ORDER.some((level) => sev[level] || deltas?.[level]) ? (
            <span className="principle-detail-sev-row">
              {SEVERITY_ORDER.map((level) => (sev[level] > 0 || Boolean(deltas?.[level])) && (
                <SevBadge
                  key={level}
                  level={level}
                  count={sev[level] || 0}
                  delta={deltas?.[level]}
                  onClick={onNavigate ? onSeverityBadge(level) : undefined}
                />
              ))}
            </span>
          ) : null}
          onClick={onNavigate && allViolations.length > 0 ? () => onCardNavigate(HERO_CARD_KIND.VIOLATIONS) : undefined}
          ariaLabel={allViolations.length > 0 ? t('overview.showAllViolationsAria') : undefined}
        />
        <Stat
          label={t('overview.statCompliance')}
          value={totalCompliant}
          hint={t('overview.passingChecks', { count: totalCompliant + allViolations.length })}
          onClick={onNavigate && totalCompliant > 0 ? () => onCardNavigate('compliance') : undefined}
          ariaLabel={totalCompliant > 0 ? t('overview.showComplianceAria') : undefined}
        />
        <RatioDensityStat ratio={ratioDisplay(allViolations.length, totalCompliant)} density={density} />
      </StatGrid2x2>

      <DimensionScoreHistoryPanel
        trend={trend}
        dimension={dimension}
        selectedRunId={activeRunId}
        granularity={granularity}
        onGranularityChange={onGranularityChange}
        onBarClick={onBarClick}
      />
    </div>
  );
}
