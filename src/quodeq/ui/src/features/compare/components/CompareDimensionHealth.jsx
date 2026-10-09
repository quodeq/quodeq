/**
 * Dimension health across the fleet, weakest first. Each row: the fleet
 * average, 30-day movement, a grade-mix bar (how many projects sit in each
 * grade, counts written in), how many are below good, the weakest project
 * and the violation total. A row opens that dimension's standings. On a
 * phone: name, fleet average, grade mix and below good.
 */
import { t } from '../../../strings/index.js';
import { scoreColorClass, scoreGradeColorVar } from '../../../utils/formatters.js';
import { getGradeThresholds } from '../../../utils/gradeThresholds.js';
import ComparePanel from './ComparePanel.jsx';
import CompareDeltaBadge from './CompareDeltaBadge.jsx';
import { LOWEST_TIER_LABEL, dimensionHealth } from '../compareFleetOverview.js';
import { nf, score1 } from '../compareFormatters.js';

// A score inside the lowest tier, to colour its segment like the scores in it.
const LOWEST_TIER_SAMPLE = 1;

/* Each tier's colour: the grade colour of the tier's own threshold. */
function tierColours() {
  const map = new Map(getGradeThresholds().map(([threshold, label]) => [label, scoreGradeColorVar(threshold)]));
  map.set(LOWEST_TIER_LABEL, scoreGradeColorVar(LOWEST_TIER_SAMPLE));
  return map;
}

function GradeMix({ mix, colours }) {
  return (
    <span className="compare-health__mix" title={mix.map((m) => t('compare.healthMixPart', { count: m.count, grade: m.label.toLowerCase() })).join(' · ')}>
      {mix.map((m) => (
        <span key={m.label} className="compare-health__seg" style={{ flexGrow: m.count, '--seg': colours.get(m.label) }}>{m.count}</span>
      ))}
    </span>
  );
}

function Head() {
  return (
    <div className="compare-health__row compare-health__row--head" aria-hidden="true">
      <span>{t('compare.healthColDimension')}</span>
      <span className="compare-health__num">{t('compare.healthColFleet')}</span>
      <span className="compare-health__num">{t('compare.col30d')}</span>
      <span>{t('compare.healthColMix')}</span>
      <span className="compare-health__num">{t('compare.healthColBelow')}</span>
      <span>{t('compare.healthColWeakest')}</span>
      <span className="compare-health__num">{t('compare.healthColViolations')}</span>
      <span />
    </div>
  );
}

export default function CompareDimensionHealth({ board, openDimension }) {
  const rows = dimensionHealth(board);
  const colours = tierColours();
  return (
    <ComparePanel ariaLabel={t('compare.healthAria')} header={t('compare.healthHeader', { count: rows.length })} note={t('compare.healthNote')}>
      <Head />
      <ul className="compare-health">
        {rows.map((d) => (
          <li key={d.key}>
            <button type="button" className="compare-health__row" onClick={() => openDimension(d.key)}>
              <span className="compare-health__label">{d.label}</span>
              <span className={`compare-health__num compare-health__avg ${scoreColorClass(d.avg)}`}>{score1(d.avg)}</span>
              <span className="compare-health__num"><CompareDeltaBadge delta={d.delta} /></span>
              <GradeMix mix={d.mix} colours={colours} />
              <span className={`compare-health__num${d.below ? ' compare-health__warn' : ''}`}>{t('compare.healthBelow', { below: d.below, total: d.total })}</span>
              <span className="compare-health__weakest">
                {d.weakest && <>{d.weakest.name} <b className={scoreColorClass(d.weakest.score)}>{score1(d.weakest.score)}</b></>}
              </span>
              <span className="compare-health__num">{nf(d.violations)}</span>
              <span className="compare-health__go" aria-hidden="true">›</span>
            </button>
          </li>
        ))}
      </ul>
      <div className="compare-health__legend" aria-label={t('compare.healthLegendAria')}>
        {[...colours].map(([label, colour]) => (
          <span key={label}><span className="compare-health__swatch" style={{ '--seg': colour }} />{label.toLowerCase()}</span>
        ))}
      </div>
    </ComparePanel>
  );
}
