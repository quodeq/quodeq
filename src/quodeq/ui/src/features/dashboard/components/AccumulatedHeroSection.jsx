import TrendBadge from '../../../components/TrendBadge.jsx';
import { gradeLetter, complianceRatio, extDisplayName } from '../../../utils/formatters.js';
import { TermHeader, Stat } from '../../../components/terminal/index.js';
import { HeroPanel, ComplianceAndRatioStats, heroCardHandlers } from './heroSectionParts.jsx';
import LastFetchedLine from '../../../components/LastFetchedLine.jsx';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import SeverityBadgeRow from './SeverityBadgeRow.jsx';
import { t } from '../../../strings/index.js';

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

export function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate, projectInfo, onCardNavigate, selectedSource, customFormula = false }) {
  const summary = accumulated?.summary;
  const scoreNum = parseFloat(summary?.numericAverage);
  const scoreDisplay = isNaN(scoreNum) ? '—' : scoreNum.toFixed(1);
  const grade = summary?.overallGrade;
  const violations = summary?.totalViolations || 0;
  const compliance = summary?.totalCompliance || 0;
  const totalChecks = violations + compliance;
  const ratio = complianceRatio(violations, compliance);

  const { handleViolations, handleCompliance, handleSeverity } = heroCardHandlers(onCardNavigate, { violations, compliance });

  return (
    <HeroPanel
      header={<>
        <TermHeader
          name={t('overview.termName')}
          sub={buildLanguageSub(projectInfo) || (lastDate ? t('overview.lastEvaluated', { date: lastDate }) : null)}
          badge={selectedSource === 'shared' ? <SharedReadOnlyBadge publishedBy={projectInfo?.publishedBy} /> : null}
        />
        <LastFetchedLine lastFetchedAt={projectInfo?.lastFetchedAt} />
      </>}
    >
      <AccumulatedStatStrip
        scoreDisplay={scoreDisplay}
        scoreDelta={scoreDelta}
        grade={grade}
        customFormula={customFormula}
        violations={violations}
        compliance={compliance}
        totalChecks={totalChecks}
        ratio={ratio}
        handleViolations={handleViolations}
        handleCompliance={handleCompliance}
        handleSeverity={handleSeverity}
        severity={summary?.severity}
      />
    </HeroPanel>
  );
}
