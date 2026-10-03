import ComparePanel from './ComparePanel.jsx';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { DuelBars, gapClass, SideScore, signed1 } from './compareDuelShared.jsx';

/**
 * @param {object} props
 * @param {{key: string, label: string, a: number|null, b: number|null, gap: number|null}[]} props.dimensions
 * @param {string} props.aName - Left/first project, for the score labels.
 * @param {string} props.bName - Right/second project, for the score labels.
 */
export default function CompareDuelDimensionsTable({ dimensions, aName, bName }) {
  return (
    <ComparePanel ariaLabel={t('compare.duelDimsAria')} header={t('compare.dimensionsHeader', { count: dimensions.length })} note={t('compare.duelDimsNote')}>
      <ul className="compare-duel-dims">
        {dimensions.map((d) => (
          <li key={d.key} className="compare-duel-dims__row">
            <span className="compare-duel-dims__label">{d.label}</span>
            {/* Which side a number belongs to is otherwise only its column
                position, which is not exposed as text (U-ACC-1). */}
            <SideScore
              className={`compare-duel-dims__score ${scoreColorClass(d.a)}`}
              project={aName}
              score={d.a}
            />
            <DuelBars a={d.a} b={d.b} />
            <SideScore
              className={`compare-duel-dims__score ${scoreColorClass(d.b)}`}
              project={bName}
              score={d.b}
            />
            <span className={`compare-duel__gap ${gapClass(d.gap)}`}>
              {d.gap != null ? signed1(d.gap) : '—'}
            </span>
          </li>
        ))}
      </ul>
    </ComparePanel>
  );
}
