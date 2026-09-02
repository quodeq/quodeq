import { TermHeader, StatStrip, Stat } from '../../../components/terminal/index.js';
import { formatRunId, gradeLetter, complianceRatio } from '../../../utils/formatters.js';
import SeverityBadgeRow from './SeverityBadgeRow.jsx';
import { t } from '../../../strings/index.js';

function RunStatStrip({ scoreDisplay, grade, violations, compliance, suppressed, totalChecks, ratio, handleViolations, handleCompliance, handleSeverity, severity }) {
  return (
    <StatStrip cards>
      <Stat
        label={t('overview.statScore')}
        value={scoreDisplay}
        hint={grade ? t('overview.gradeHint', { letter: gradeLetter(grade) }) : null}
      />
      <Stat
        label={t('overview.statViolations')}
        value={violations}
        hint={
          <>
            <SeverityBadgeRow severity={severity} onSeverityClick={handleSeverity} />
            {suppressed > 0 && (
              <span className="term-stat__suppressed-note">{t('overview.runSuppressed', { count: suppressed })}</span>
            )}
          </>
        }
        onClick={handleViolations}
        ariaLabel={violations > 0 ? t('overview.showRunViolationsAria') : undefined}
      />
      <Stat
        label={t('overview.statCompliance')}
        value={compliance}
        hint={totalChecks > 0 ? t('overview.passingChecks', { count: totalChecks }) : null}
        onClick={handleCompliance}
        ariaLabel={compliance > 0 ? t('overview.showRunComplianceAria') : undefined}
      />
      <Stat
        label={t('overview.statRatio')}
        value={ratio}
        hint={t('overview.ratioHint')}
      />
    </StatStrip>
  );
}

export function RunHeroSection({ dashboard, selectedRunId, runSummary, onCardNavigate }) {
  const dateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId);
  const scoreNum = parseFloat(runSummary.numericAverage);
  const scoreDisplay = isNaN(scoreNum) ? '—' : scoreNum.toFixed(1);
  const grade = runSummary.overallGrade;
  const violations = runSummary.totalViolations || 0;
  const compliance = runSummary.totalCompliance || 0;
  const suppressed = runSummary.suppressed || 0;
  const totalChecks = violations + compliance;
  const ratio = complianceRatio(violations, compliance);

  const handleViolations = onCardNavigate && violations > 0 ? () => onCardNavigate('violations') : undefined;
  const handleCompliance = onCardNavigate && compliance > 0 ? () => onCardNavigate('compliance') : undefined;
  const handleSeverity = onCardNavigate ? (level) => onCardNavigate(level) : undefined;

  return (
    <section className="acc-eval-panel acc-eval-panel--terminal">
      <div className="acc-eval-panel__top">
        <TermHeader name={t('overview.termNameRun')} sub={dateLabel} />
      </div>
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
      />
    </section>
  );
}
