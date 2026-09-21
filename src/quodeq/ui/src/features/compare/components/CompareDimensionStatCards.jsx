import { StatStrip, Stat } from '../../../components/terminal/index.js';
import { SeverityCardHint } from './severityCells.jsx';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t } from '../../../strings/index.js';
import { nf, score1 } from '../compareFormatters.js';

// Below the midpoint of the 0-10 score scale: the weakest-principle stat
// renders with critical tone instead of the default.
const CRITICAL_SCORE_THRESHOLD = 5;

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
          <SeverityCardHint severity={view.severity} />
        )}
      />
      <Stat
        label={t('compare.cardWeakest')}
        value={view.weakest ? view.weakest.label : '—'}
        hint={view.weakest ? t('compare.weakestNote', { score: score1(view.weakest.avg) }) : ''}
        tone={view.weakest && view.weakest.avg != null && view.weakest.avg < CRITICAL_SCORE_THRESHOLD ? 'critical' : 'default'}
      />
    </StatStrip>
  );
}
