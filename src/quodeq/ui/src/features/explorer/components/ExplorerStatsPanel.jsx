import { Stat, SevBadge } from '../../../components/terminal/index.js';
import { complianceRatio } from '../../../utils/formatters.js';
import StatGrid2x2 from './StatGrid2x2.jsx';
import DimensionScoreHistoryPanel from './DimensionScoreHistoryPanel.jsx';
import { t } from '../../../strings/index.js';

// The three buckets the violations stat summarises, most severe first.
const SUMMARY_SEVERITIES = ['critical', 'major', 'minor'];

/** The score/violations/compliance/ratio stat grid + the run-history bar
 * chart — the left column of the dimension page's top grid. */
export default function ExplorerStatsPanel({
  overallScoreNum, overallGrade, allViolations, totalCompliant, sev, onSeverityBadge,
  onNavigate, onCardNavigate, trend, dimension, activeRunId, granularity, onGranularityChange, onBarClick,
}) {
  return (
    <div className="qd-top-left">
      <StatGrid2x2>
        <Stat
          label={t('overview.statScore')}
          value={Number.isNaN(overallScoreNum) ? '—' : overallScoreNum.toFixed(1)}
          hint={overallGrade?.grade ? t('overview.gradeHint', { letter: overallGrade.grade }) : null}
        />
        <Stat
          label={t('overview.statViolations')}
          value={allViolations.length}
          hint={(sev.critical || sev.major || sev.minor) ? (
            <span className="principle-detail-sev-row">
              {SUMMARY_SEVERITIES.map((level) => sev[level] > 0 && (
                <SevBadge
                  key={level}
                  level={level}
                  count={sev[level]}
                  onClick={onNavigate ? onSeverityBadge(level) : undefined}
                />
              ))}
            </span>
          ) : null}
          onClick={onNavigate && allViolations.length > 0 ? () => onCardNavigate('violations') : undefined}
          ariaLabel={allViolations.length > 0 ? t('overview.showAllViolationsAria') : undefined}
        />
        <Stat
          label={t('overview.statCompliance')}
          value={totalCompliant}
          hint={t('overview.passingChecks', { count: totalCompliant + allViolations.length })}
          onClick={onNavigate && totalCompliant > 0 ? () => onCardNavigate('compliance') : undefined}
          ariaLabel={totalCompliant > 0 ? t('overview.showComplianceAria') : undefined}
        />
        <Stat
          label={t('overview.statRatio')}
          value={complianceRatio(allViolations.length, totalCompliant)}
          hint={t('overview.ratioHint')}
        />
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
