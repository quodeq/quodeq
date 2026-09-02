import { SectionLabel } from '../../../components/terminal/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { DuelBars, gapClass, score1, signed1 } from './compareDuelShared.jsx';

function PrincipleGroup({ group, dim }) {
  return (
    <article className="compare-duel-principles__group">
      <h3 className="compare-duel-principles__dim">
        <span className="compare-duel-principles__dimLabel">{group.label}</span>
        {dim && (
          /* Legend-style side swatches (the same dash language the charts'
             legends use) tie each number to its side without repeating the
             row bars up here. */
          <span className="compare-duel-principles__dimScores">
            <span className="compare-duel-principles__side compare-duel-principles__side--a" aria-hidden="true" />
            <span className={scoreColorClass(dim.a)}>{score1(dim.a)}</span>
            <span className="compare-duel-principles__side compare-duel-principles__side--b" aria-hidden="true" />
            <span className={scoreColorClass(dim.b)}>{score1(dim.b)}</span>
            <span className={`compare-duel__gap ${gapClass(dim.gap)}`}>
              {dim.gap != null ? signed1(dim.gap) : '—'}
            </span>
          </span>
        )}
      </h3>
      <ul className="compare-duel-principles__list">
        {group.items.map((p) => (
          <li key={p.key} className="compare-duel-principles__row">
            <span className="compare-duel-principles__label">{p.label}</span>
            <span className={`compare-duel-principles__score ${scoreColorClass(p.a)}`}>{score1(p.a)}</span>
            <DuelBars a={p.a} b={p.b} />
            <span className={`compare-duel-principles__score ${scoreColorClass(p.b)}`}>{score1(p.b)}</span>
            <span className={`compare-duel__gap ${gapClass(p.gap)}`}>
              {p.gap != null ? signed1(p.gap) : '—'}
            </span>
          </li>
        ))}
      </ul>
    </article>
  );
}

/** Per-principle diffs, one group per shared dimension. The group heading
 * repeats that dimension's two scores + gap so the diff reads without
 * scrolling back up to the dimensions table. */
export default function CompareDuelPrinciples({ principles, dimensions }) {
  const count = principles.reduce((n, g) => n + g.items.length, 0);
  return (
    <section className="compare-panel" aria-label={t('compare.duelPrinciplesAria')}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.duelPrinciplesHeader', { count })}</SectionLabel>
        <span className="compare-panel__note">{t('compare.duelPrinciplesNote')}</span>
      </div>
      {principles.length ? (
        <div className="compare-duel-principles">
          {principles.map((group) => (
            <PrincipleGroup
              key={group.key}
              group={group}
              dim={dimensions.find((d) => d.key === group.key)}
            />
          ))}
        </div>
      ) : (
        <p className="compare-panel__fallback">{t('compare.duelNoShared')}</p>
      )}
    </section>
  );
}
