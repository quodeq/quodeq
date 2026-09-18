import { SectionLabel } from '../../../components/terminal/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { DuelBars, gapClass, score1, signed1 } from './compareDuelShared.jsx';

/**
 * @param {object} props
 * @param {{key: string, label: string, a: number|null, b: number|null, gap: number|null}[]} props.dimensions
 * @param {string} props.aName - Left/first project, for the score labels.
 * @param {string} props.bName - Right/second project, for the score labels.
 */
export default function CompareDuelDimensionsTable({ dimensions, aName, bName }) {
  return (
    <section className="compare-panel" aria-label={t('compare.duelDimsAria')}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.dimensionsHeader', { count: dimensions.length })}</SectionLabel>
        <span className="compare-panel__note">{t('compare.duelDimsNote')}</span>
      </div>
      <ul className="compare-duel-dims">
        {dimensions.map((d) => (
          <li key={d.key} className="compare-duel-dims__row">
            <span className="compare-duel-dims__label">{d.label}</span>
            {/* Which side a number belongs to is otherwise only its column
                position, which is not exposed as text (U-ACC-1). */}
            <span
              className={`compare-duel-dims__score ${scoreColorClass(d.a)}`}
              aria-label={t('compare.sideScoreAria', { project: aName, score: score1(d.a) })}
            >
              {score1(d.a)}
            </span>
            <DuelBars a={d.a} b={d.b} />
            <span
              className={`compare-duel-dims__score ${scoreColorClass(d.b)}`}
              aria-label={t('compare.sideScoreAria', { project: bName, score: score1(d.b) })}
            >
              {score1(d.b)}
            </span>
            <span className={`compare-duel__gap ${gapClass(d.gap)}`}>
              {d.gap != null ? signed1(d.gap) : '—'}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
