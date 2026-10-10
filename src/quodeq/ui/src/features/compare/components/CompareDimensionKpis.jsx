/**
 * One dimension across the scope, in six numbers: its score and 30-day
 * movement, how many projects sit below good, coverage (how many projects
 * in scope have it scored at all), violation density and critical findings
 * per size for this dimension, and the spread. The same strip as the fleet
 * overview, one level down.
 */
import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import CompareDeltaBadge from './CompareDeltaBadge.jsx';
import { CriticalKpi, Kpi } from './CompareFleetKpis.jsx';
import { dimensionKpis } from '../compareDimensionOverview.js';
import { score1 } from '../compareFormatters.js';

const NONE = '·';
const fixed1 = (v) => (v == null ? NONE : v.toFixed(1));
const ofTotal = (n, total) => `${n}/${total}`;

export default function CompareDimensionKpis({ view, rows, scopeCount }) {
  const k = dimensionKpis(view, rows, scopeCount);
  const dim = view.label;
  return (
    <section className="compare-kpis" aria-label={t('compare.dimKpisAria', { dim })}>
      <Kpi
        label={t('compare.dimKpiScore', { dim })}
        value={score1(k.score)}
        valueClass={scoreColorClass(k.score)}
        sub={t('compare.dimKpiScoreSub', { grade: scoreToGradeLabel(k.score) || NONE })}
      >
        <CompareDeltaBadge delta={k.delta} />
      </Kpi>
      <Kpi
        label={t('compare.dimKpiBelow')}
        value={ofTotal(k.below, k.projects)}
        valueClass={k.below ? 'compare-kpi__value--alarm' : ''}
        sub={t('compare.dimKpiBelowSub')}
      />
      <Kpi label={t('compare.dimKpiCoverage')} value={ofTotal(k.projects, k.scope)} sub={t('compare.dimKpiCoverageSub', { dim })} />
      <Kpi label={t('compare.kpiDensity')} value={fixed1(k.density)} sub={t('compare.dimKpiDensitySub')} />
      <CriticalKpi critical={k.critical} criticalPerK={k.criticalPerK} />
      <Kpi
        desktopOnly
        label={t('compare.kpiSpread')}
        value={fixed1(k.spread)}
        sub={k.lead && k.trail && k.lead !== k.trail
          ? t('compare.kpiSpreadSub', { lead: k.lead.row.name, leadScore: score1(k.lead.score), trail: k.trail.row.name, trailScore: score1(k.trail.score) })
          : NONE}
      />
    </section>
  );
}
