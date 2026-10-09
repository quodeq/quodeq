/**
 * Principle health within one dimension, weakest first: the average, a
 * grade-mix bar, how many projects are below good, coverage (how many of the
 * dimension's projects scored the principle: an average over 2 of 9 is
 * thin, and says so) and the leader and trailer. A row opens the trailer's
 * principle page, where the fix is.
 */
import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import ComparePanel from './ComparePanel.jsx';
import { GradeMix, tierColours } from './CompareDimensionHealth.jsx';
import { principleHealth } from '../compareDimensionOverview.js';
import { score1 } from '../compareFormatters.js';

const NONE = '·';

function Who({ entry }) {
  if (!entry) return <span className="compare-ph__who">{NONE}</span>;
  return (
    <span className="compare-ph__who">
      {entry.name} <b className={scoreColorClass(entry.score)}>{score1(entry.score)}</b>
    </span>
  );
}

function Head() {
  return (
    <div className="compare-ph compare-ph--head" aria-hidden="true">
      <span>{t('compare.phColPrinciple')}</span>
      <span className="compare-ph__num">{t('compare.phColAvg')}</span>
      <span>{t('compare.healthColMix')}</span>
      <span className="compare-ph__num">{t('compare.healthColBelow')}</span>
      <span className="compare-ph__num">{t('compare.phColCoverage')}</span>
      <span>{t('compare.phColLead')}</span>
      <span>{t('compare.phColTrail')}</span>
    </div>
  );
}

export default function ComparePrincipleHealth({ view, onOpenPrinciple }) {
  const rows = principleHealth(view);
  const colours = tierColours();
  return (
    <ComparePanel ariaLabel={t('compare.phAria', { dim: view.label })} header={t('compare.phHeader', { count: rows.length })} note={t('compare.phNote')}>
      <Head />
      <ul className="compare-ph__list">
        {rows.map((p) => (
          <li key={p.key}>
            <button type="button" className="compare-ph" onClick={() => p.trail && onOpenPrinciple?.(p.trail)}>
              <span className="compare-ph__label">{p.label}</span>
              <span className={`compare-ph__num compare-ph__avg ${scoreColorClass(p.avg)}`}>{score1(p.avg)}</span>
              <GradeMix mix={p.mix} colours={colours} />
              <span className={`compare-ph__num${p.below ? ' compare-ph__warn' : ''}`}>{t('compare.healthBelow', { below: p.below, total: p.total })}</span>
              <span className={`compare-ph__num${p.total * 2 < p.of ? ' compare-ph__warn' : ''}`}>{t('compare.phCoverage', { scored: p.total, total: p.of })}</span>
              <Who entry={p.lead} />
              <Who entry={p.trail} />
            </button>
          </li>
        ))}
      </ul>
    </ComparePanel>
  );
}
