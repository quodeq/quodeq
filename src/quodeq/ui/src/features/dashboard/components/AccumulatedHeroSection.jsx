import TrendBadge from '../../../components/TrendBadge.jsx';
import { gradeLetter, complianceRatio, extDisplayName } from '../../../utils/formatters.js';
import { formatScoreDisplay } from '../../../utils/gradeFormatting.js';
import { TermHeader, Stat } from '../../../components/terminal/index.js';
import { HeroPanel, ComplianceAndRatioStats, heroCardHandlers } from './heroSectionParts.jsx';
import LastFetchedLine from '../../../components/LastFetchedLine.jsx';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import SeverityBadgeRow from './SeverityBadgeRow.jsx';
import { t } from '../../../strings/index.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

const MAX_LANGS_IN_SUB = 5;

function buildLanguageSub(projectInfo) {
  const stats = projectInfo?.languageStats;
  if (!stats) return null;
  const sorted = Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, MAX_LANGS_IN_SUB);
  if (sorted.length === 0) return null;
  return sorted
    .map(([lang, count]) => `${count} ${extDisplayName(lang).toLowerCase()}`)
    .join('  ');
}

function AccumulatedStatStrip({ scoreDisplay, scoreDelta, grade, customFormula, violations, compliance, totalChecks, ratio, handleViolations, handleCompliance, handleSeverity, severity }) {
  return (
    <>
      <Stat
        label={t('overview.statScore')}
        value={scoreDisplay}
        trailing={scoreDelta !== null ? <TrendBadge delta={scoreDelta} showLabel={false} /> : null}
        // A tuned formula shifts every score at once with no other trace, so
        // say so where the grade is read rather than only on the settings
        // page that changed it.
        hint={grade
          ? t(customFormula ? 'overview.gradeHintCustomFormula' : 'overview.gradeHint',
              { letter: gradeLetter(grade) })
          : null}
      />
      <Stat
        label={t('overview.statViolations')}
        value={violations}
        hint={<SeverityBadgeRow severity={severity} onSeverityClick={handleSeverity} />}
        onClick={handleViolations}
        ariaLabel={violations > 0 ? t('overview.showAllViolationsAria') : undefined}
      />
      <ComplianceAndRatioStats
        compliance={compliance}
        totalChecks={totalChecks}
        ratio={ratio}
        onCompliance={handleCompliance}
        complianceAriaKey="overview.showComplianceAria"
      />
    </>
  );
}

/** Numbers the stat strip shows, read off the accumulated summary. */
function accumulatedStats(summary) {
  const violations = summary?.totalViolations || 0;
  const compliance = summary?.totalCompliance || 0;
  return {
    scoreDisplay: formatScoreDisplay(summary?.numericAverage),
    grade: summary?.overallGrade,
    violations,
    compliance,
    totalChecks: violations + compliance,
    ratio: complianceRatio(violations, compliance),
    severity: summary?.severity,
  };
}

/** Sub-line under the term header: the language mix, else the last run date. */
function heroSubLine(projectInfo, lastDate) {
  return buildLanguageSub(projectInfo)
    || (lastDate ? t('overview.lastEvaluated', { date: lastDate }) : null);
}

export function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate, projectInfo, onCardNavigate, selectedSource, customFormula = false }) {
  const stats = accumulatedStats(accumulated?.summary);
  const { handleViolations, handleCompliance, handleSeverity } = heroCardHandlers(
    onCardNavigate,
    { violations: stats.violations, compliance: stats.compliance },
  );

  return (
    <HeroPanel
      header={<>
        <TermHeader
          name={t('overview.termName')}
          sub={heroSubLine(projectInfo, lastDate)}
          badge={selectedSource === PROJECT_SOURCE.SHARED ? <SharedReadOnlyBadge publishedBy={projectInfo?.publishedBy} /> : null}
        />
        <LastFetchedLine lastFetchedAt={projectInfo?.lastFetchedAt} />
      </>}
    >
      <AccumulatedStatStrip
        {...stats}
        scoreDelta={scoreDelta}
        customFormula={customFormula}
        handleViolations={handleViolations}
        handleCompliance={handleCompliance}
        handleSeverity={handleSeverity}
      />
    </HeroPanel>
  );
}
