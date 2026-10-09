/**
 * Where the fleet stands, in six numbers: score (and weighted by size),
 * codebase size, violation density, critical findings, freshness and
 * spread. Exposure is per size, so a big project is not "worse" for being
 * big. On a phone, codebase and spread drop (the file total is in the page
 * subtitle; the spread is the top and bottom of the ranking).
 */
import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import CompareDeltaBadge from './CompareDeltaBadge.jsx';
import { fleetKpis } from '../compareFleetOverview.js';
import { nf, score1 } from '../compareFormatters.js';

const NONE = '·';
const fixed1 = (v) => (v == null ? NONE : v.toFixed(1));

export function Kpi({ label, value, valueClass = '', sub, desktopOnly = false, children = null }) {
  return (
    <div className={`compare-kpi${desktopOnly ? ' compare-fleet__desktop' : ''}`}>
      <span className="compare-kpi__label">{label}</span>
      <span className={`compare-kpi__value ${valueClass}`}>{value}{children}</span>
      <span className="compare-kpi__sub">{sub}</span>
    </div>
  );
}

/** Critical findings, alarmed when any, with the count per 1,000 files. */
export function CriticalKpi({ critical, criticalPerK }) {
  return (
    <Kpi
      label={t('compare.kpiCritical')}
      value={nf(critical)}
      valueClass={critical ? 'compare-kpi__value--alarm' : ''}
      sub={t('compare.kpiCriticalSub', { value: fixed1(criticalPerK) })}
    />
  );
}

function spreadSub(k) {
  if (!k.lead || !k.trail) return NONE;
  return t('compare.kpiSpreadSub', { lead: k.lead.name, leadScore: score1(k.lead.score), trail: k.trail.name, trailScore: score1(k.trail.score) });
}

export default function CompareFleetKpis({ rows, fleet }) {
  const k = fleetKpis(rows, fleet);
  return (
    <section className="compare-kpis" aria-label={t('compare.kpisAria')}>
      <Kpi
        label={t('compare.kpiScore')}
        value={score1(k.score)}
        valueClass={scoreColorClass(k.score)}
        sub={t('compare.kpiScoreSub', { grade: scoreToGradeLabel(k.score) || NONE, weighted: score1(k.weighted) })}
      >
        <CompareDeltaBadge delta={k.delta} />
      </Kpi>
      <Kpi
        desktopOnly
        label={t('compare.kpiFiles')}
        value={nf(k.files)}
        sub={k.coverage != null
          ? t('compare.kpiFilesSubCoverage', { count: k.projects, pct: k.coverage })
          : t('compare.kpiFilesSub', { count: k.projects })}
      />
      <Kpi label={t('compare.kpiDensity')} value={fixed1(k.density)} sub={t('compare.kpiDensitySub')} />
      <CriticalKpi critical={k.critical} criticalPerK={k.criticalPerK} />
      <Kpi
        label={t('compare.kpiFresh')}
        value={`${k.fresh}/${k.projects}`}
        sub={k.stale ? t('compare.kpiFreshStale', { count: k.stale }) : t('compare.kpiFreshAll')}
      />
      <Kpi desktopOnly label={t('compare.kpiSpread')} value={fixed1(k.spread)} sub={spreadSub(k)} />
    </section>
  );
}
