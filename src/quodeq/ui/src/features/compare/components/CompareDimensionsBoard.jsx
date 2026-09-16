import { SectionLabel } from '../../../components/terminal/index.js';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { nf, score1 } from '../compareFormatters.js';


/** The compact per-dimension board: one row per dimension, opening its
 * drill-down. */
export default function CompareDimensionsBoard({ board, openDimension }) {
  return (
    <section className="compare-panel" aria-label={t('compare.dimensionsAria')}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.dimensionsHeader', { count: board.length })}</SectionLabel>
        <span className="compare-panel__note">{t('compare.dimensionsNote')}</span>
      </div>
      <ul className="compare-board compare-board--grid">
        {board.map((b) => (
          <li key={b.key}>
            <button type="button" className="compare-board__row" onClick={() => openDimension(b.key)}>
              <span className="compare-board__label">{b.label}</span>
              <span className={`compare-board__score ${scoreColorClass(b.avg)}`}>{score1(b.avg)}</span>
              <span className="compare-board__delta"><TrendBadge delta={b.delta} /></span>
              <span className="compare-board__viol">{t('compare.violCount', { count: nf(b.violations) })}</span>
              <span className="compare-board__chevron" aria-hidden="true">›</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
