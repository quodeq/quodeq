import ComparePanel from './ComparePanel.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { nf, score1 } from '../compareFormatters.js';


/** The compact per-dimension board: one row per dimension, opening its
 * drill-down. */
export default function CompareDimensionsBoard({ board, openDimension }) {
  return (
    <ComparePanel ariaLabel={t('compare.dimensionsAria')} header={t('compare.dimensionsHeader', { count: board.length })} note={t('compare.dimensionsNote')}>
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
    </ComparePanel>
  );
}
