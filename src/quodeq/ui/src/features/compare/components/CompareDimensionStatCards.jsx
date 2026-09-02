import { StatStrip, Stat } from '../../../components/terminal/index.js';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

/** The dimension-scoped stat cards: scope score, spread, violations, weakest
 * principle. */
export default function CompareDimensionStatCards({ view }) {
  return (
    <StatStrip cards>
      <Stat
        label={t('compare.cardScopeScore')}
        value={score1(view.avg)}
        hint={`${scoreToGradeLabel(view.avg) || ''} · ${t('compare.projectsInScope', { count: view.standings.length })}`}
      />
      <Stat
        label={t('compare.cardSpread')}
        value={view.spread != null ? score1(view.spread) : '—'}
        hint={view.lead && view.trail && view.lead !== view.trail
          ? t('compare.spreadNote', {
            lead: view.lead.row.name,
            leadScore: score1(view.lead.score),
            trail: view.trail.row.name,
            trailScore: score1(view.trail.score),
          })
          : t('compare.needTwo')}
      />
      <Stat
        label={t('compare.cardViolations')}
        value={nf(view.violations)}
        hint={(
          <span className="compare-card__sev">
            <SevBadge level="critical" count={view.severity.critical} />
            <SevBadge level="major" count={view.severity.major} />
            <SevBadge level="minor" count={view.severity.minor} />
          </span>
        )}
      />
      <Stat
        label={t('compare.cardWeakest')}
        value={view.weakest ? view.weakest.label : '—'}
        hint={view.weakest ? t('compare.weakestNote', { score: score1(view.weakest.avg) }) : ''}
        tone={view.weakest && view.weakest.avg != null && view.weakest.avg < 5 ? 'critical' : 'default'}
      />
    </StatStrip>
  );
}
