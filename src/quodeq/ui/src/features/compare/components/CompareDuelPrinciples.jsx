import ComparePanel from './ComparePanel.jsx';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { DuelBars, gapClass, SideScore, signed1 } from './compareDuelShared.jsx';

function PrincipleGroup({ group, dim, aName, bName }) {
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
            <SideScore className={scoreColorClass(dim.a)} project={aName} score={dim.a} />
            <span className="compare-duel-principles__side compare-duel-principles__side--b" aria-hidden="true" />
            <SideScore className={scoreColorClass(dim.b)} project={bName} score={dim.b} />
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
            <SideScore
              className={`compare-duel-principles__score ${scoreColorClass(p.a)}`}
              project={aName}
              score={p.a}
            />
            <DuelBars a={p.a} b={p.b} />
            <SideScore
              className={`compare-duel-principles__score ${scoreColorClass(p.b)}`}
              project={bName}
              score={p.b}
            />
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
export default function CompareDuelPrinciples({ principles, dimensions, aName, bName }) {
  const count = principles.reduce((n, g) => n + g.items.length, 0);
  // Dimension lookup keyed once, not a find() per principle group.
  const dimByKey = new Map(dimensions.map((d) => [d.key, d]));
  return (
    <ComparePanel ariaLabel={t('compare.duelPrinciplesAria')} header={t('compare.duelPrinciplesHeader', { count })} note={t('compare.duelPrinciplesNote')}>
      {principles.length ? (
        <div className="compare-duel-principles">
          {principles.map((group) => (
            <PrincipleGroup
              key={group.key}
              group={group}
              dim={dimByKey.get(group.key)}
              aName={aName}
              bName={bName}
            />
          ))}
        </div>
      ) : (
        <p className="compare-panel__fallback">{t('compare.duelNoShared')}</p>
      )}
    </ComparePanel>
  );
}
