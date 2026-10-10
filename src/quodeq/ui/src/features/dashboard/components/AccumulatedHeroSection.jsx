import TrendBadge from '../../../components/TrendBadge.jsx';
import { extDisplayName } from '../../../utils/formatters.js';
import { formatScoreDisplay } from '../../../utils/gradeFormatting.js';
import { TermHeader, Stat } from '../../../components/terminal/index.js';
import { HeroPanel, ComplianceAndRatioStats, ScoreStat, heroCardHandlers, ratioDisplay } from './heroSectionParts.jsx';
import LastFetchedLine from '../../../components/LastFetchedLine.jsx';
import SharedReadOnlyBadge from '../../../components/SharedReadOnlyBadge.jsx';
import SeverityBadgeRow from './SeverityBadgeRow.jsx';
import { t, LOCALE } from '../../../strings/index.js';
import { PROJECT_SOURCE } from '../../../vocab/projectSource.js';

const MAX_LANGS_IN_SUB = 5;

// The project's size first ("3,925 files"), then its top languages.
function buildLanguageSub(projectInfo) {
  const files = projectInfo?.filesCount;
  const total = files != null ? t('overview.filesTotal', { count: files.toLocaleString(LOCALE) }) : null;
  const stats = projectInfo?.languageStats;
  const sorted = stats ? Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, MAX_LANGS_IN_SUB) : [];
  const langs = sorted.map(([lang, count]) => `${count} ${extDisplayName(lang).toLowerCase()}`).join('  ');
  if (!total) return langs || null;
  return langs ? `${total}  ·  ${langs}` : total;
}

function AccumulatedStatStrip({ scoreDisplay, scoreDelta, grade, customFormula, violations, compliance, totalChecks, ratio, handleViolations, handleCompliance, handleSeverity, severity, deltas, density }) {
  return (
    <>
      {/* A tuned formula shifts every score at once with no other trace, so
          say so where the grade is read rather than only on the settings
          page that changed it. */}
      <ScoreStat
        scoreDisplay={scoreDisplay}
        grade={grade}
        extraTrailing={scoreDelta !== null ? <TrendBadge delta={scoreDelta} showLabel={false} /> : null}
        hint={customFormula ? t('overview.customFormulaNote') : null}
      />
      <Stat
        label={t('overview.statViolations')}
        value={violations}
        hint={<SeverityBadgeRow severity={severity} onSeverityClick={handleSeverity} deltas={deltas} />}
        onClick={handleViolations}
        ariaLabel={violations > 0 ? t('overview.showAllViolationsAria') : undefined}
      />
      <ComplianceAndRatioStats compliance={compliance} totalChecks={totalChecks} ratio={ratio} density={density} onCompliance={handleCompliance} complianceAriaKey="overview.showComplianceAria" />
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
    ratio: ratioDisplay(violations, compliance),
    severity: summary?.severity,
  };
}

/** Sub-line under the term header: the size and language mix, else the last run date. */
function heroSubLine(projectInfo, lastDate) {
  return buildLanguageSub(projectInfo)
    || (lastDate ? t('overview.lastEvaluated', { date: lastDate }) : null);
}

export function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate, projectInfo, onCardNavigate, selectedSource, customFormula = false, deltas = null, density = null, pending = false }) {
  const stats = accumulatedStats(accumulated?.summary);
  const { handleViolations, handleCompliance, handleSeverity } = heroCardHandlers(
    onCardNavigate,
    { violations: stats.violations, compliance: stats.compliance },
  );

  return (
    <HeroPanel
      pending={pending}
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
        deltas={deltas}
        density={density}
        handleViolations={handleViolations}
        handleCompliance={handleCompliance}
        handleSeverity={handleSeverity}
      />
    </HeroPanel>
  );
}
