import { StatStrip, Stat } from '../../../components/terminal/index.js';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

/** The fleet-wide stat cards: scope score, violations, compliance, spread. */
export default function CompareFleetStatCards({ fleet }) {
  return (
    <StatStrip cards>
      <Stat
        label={t('compare.cardScopeScore')}
        value={score1(fleet.score)}
        hint={fleet.score != null
          ? `${scoreToGradeLabel(fleet.score) || ''} · ${t('compare.projectsInScope', { count: fleet.scoredCount })}`
          : t('compare.noScores')}
        trailing={<TrendBadge delta={fleet.delta} />}
      />
      <Stat
        label={t('compare.cardViolations')}
        value={nf(fleet.totalViolations)}
        hint={(
          <span className="compare-card__sev">
            <SevBadge level="critical" count={fleet.severity.critical} />
            <SevBadge level="major" count={fleet.severity.major} />
            <SevBadge level="minor" count={fleet.severity.minor} />
          </span>
        )}
      />
      <Stat
        label={t('compare.cardCompliance')}
        value={fleet.passPct != null ? `${fleet.passPct}%` : '—'}
        hint={t('compare.passingChecks', { pass: nf(fleet.totalCompliance), checks: nf(fleet.checks) })}
      />
      <Stat
        label={t('compare.cardSpread')}
        value={fleet.spread != null ? score1(fleet.spread) : '—'}
        hint={fleet.lead && fleet.trail
          ? t('compare.spreadNote', {
            lead: fleet.lead.name,
            leadScore: score1(fleet.lead.score),
            trail: fleet.trail.name,
            trailScore: score1(fleet.trail.score),
          })
          : t('compare.needTwo')}
      />
    </StatStrip>
  );
}
