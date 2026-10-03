import { TermHeader, Stat } from '../../../components/terminal/index.js';
import { HeroPanel, ComplianceAndRatioStats, ScoreStat, heroCardHandlers, ratioDisplay } from './heroSectionParts.jsx';
import { formatRunId } from '../../../utils/formatters.js';
import { formatScoreDisplay } from '../../../utils/gradeFormatting.js';
import SeverityBadgeRow from './SeverityBadgeRow.jsx';
import { t } from '../../../strings/index.js';

function RunStatStrip({ scoreDisplay, grade, violations, compliance, suppressed, totalChecks, ratio, handleViolations, handleCompliance, handleSeverity, severity, deltas, density }) {
  return (
    <>
      <ScoreStat scoreDisplay={scoreDisplay} grade={grade} />
      <Stat
        label={t('overview.statViolations')}
        value={violations}
        hint={
          <>
            <SeverityBadgeRow severity={severity} onSeverityClick={handleSeverity} deltas={deltas} />
            {suppressed > 0 && (
              <span className="term-stat__suppressed-note">{t('overview.runSuppressed', { count: suppressed })}</span>
            )}
          </>
        }
        onClick={handleViolations}
        ariaLabel={violations > 0 ? t('overview.showRunViolationsAria') : undefined}
      />
      <ComplianceAndRatioStats compliance={compliance} totalChecks={totalChecks} ratio={ratio} density={density} onCompliance={handleCompliance} complianceAriaKey="overview.showRunComplianceAria" />
    </>
  );
}

export function RunHeroSection({ dashboard, selectedRunId, runSummary, onCardNavigate, deltas = null, density = null }) {
  const dateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId);
  const scoreDisplay = formatScoreDisplay(runSummary.numericAverage);
  const grade = runSummary.overallGrade;
  const violations = runSummary.totalViolations || 0;
  const compliance = runSummary.totalCompliance || 0;
  const suppressed = runSummary.suppressed || 0;
  const totalChecks = violations + compliance;
  const ratio = ratioDisplay(violations, compliance);

  const { handleViolations, handleCompliance, handleSeverity } = heroCardHandlers(onCardNavigate, { violations, compliance });

  return (
    <HeroPanel header={<TermHeader name={t('overview.termNameRun')} sub={dateLabel} />}>
      <RunStatStrip
        scoreDisplay={scoreDisplay}
        grade={grade}
        violations={violations}
        compliance={compliance}
        suppressed={suppressed}
        totalChecks={totalChecks}
        ratio={ratio}
        handleViolations={handleViolations}
        handleCompliance={handleCompliance}
        handleSeverity={handleSeverity}
        severity={runSummary.severity}
        deltas={deltas}
        density={density}
      />
    </HeroPanel>
  );
}
