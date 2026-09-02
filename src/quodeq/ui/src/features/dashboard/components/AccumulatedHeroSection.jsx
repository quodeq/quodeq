import TrendBadge from '../../../components/TrendBadge.jsx';
import { gradeLetter, complianceRatio, extDisplayName } from '../../../utils/formatters.js';
import { TermHeader, StatStrip, Stat } from '../../../components/terminal/index.js';
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
    <StatStrip cards>
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
        onClick={violations > 0 ? handleViolations : undefined}
        ariaLabel={violations > 0 ? t('overview.showAllViolationsAria') : undefined}
      />
      <Stat
        label={t('overview.statCompliance')}
        value={compliance}
        hint={totalChecks > 0 ? t('overview.passingChecks', { count: totalChecks }) : null}
        onClick={handleCompliance}
        ariaLabel={compliance > 0 ? t('overview.showComplianceAria') : undefined}
      />
      <Stat
        label={t('overview.statRatio')}
        value={ratio}
        hint={t('overview.ratioHint')}
      />
    </StatStrip>
  );
}

export function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate, accumulatedDimensions, projectName, projectInfo, onCardNavigate, selectedSource, customFormula = false }) {
  const summary = accumulated?.summary;
  const scoreNum = parseFloat(summary?.numericAverage);
  const scoreDisplay = isNaN(scoreNum) ? '—' : scoreNum.toFixed(1);
  const grade = summary?.overallGrade;
  const violations = summary?.totalViolations || 0;
  const compliance = summary?.totalCompliance || 0;
  const totalChecks = violations + compliance;
  const ratio = complianceRatio(violations, compliance);

  const handleViolations = onCardNavigate ? () => onCardNavigate('violations') : undefined;
  const handleCompliance = onCardNavigate && compliance > 0 ? () => onCardNavigate('compliance') : undefined;
  const handleSeverity = onCardNavigate ? (level) => onCardNavigate(level) : undefined;

  return (
    <section className="acc-eval-panel acc-eval-panel--terminal">
      <div className="acc-eval-panel__top">
        <TermHeader
          name={t('overview.termName')}
          sub={buildLanguageSub(projectInfo) || (lastDate ? t('overview.lastEvaluated', { date: lastDate }) : null)}
          badge={selectedSource === 'shared' ? <SharedReadOnlyBadge publishedBy={projectInfo?.publishedBy} /> : null}
        />
        <LastFetchedLine lastFetchedAt={projectInfo?.lastFetchedAt} />
      </div>
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
    </section>
  );
}
