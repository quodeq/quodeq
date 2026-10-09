/**
 * CompareDuelView: head-to-head between exactly two projects, laid out in
 * the order an engineer or researcher asks the questions:
 *
 *   1. who leads, and is the gap bigger than run-to-run noise?  (verdict)
 *   2. is this a fair comparison?                               (checks)
 *   3. where does the gap come from? / exposure by size          (two panels)
 *   4. how did they get here?                                    (trend)
 *   5. systematic or a few outliers? what do both get wrong?     (principles)
 *   6. every number, for lookup                                  (table, on demand)
 *
 * Sides are fixed for the whole screen: A is always the first project
 * (accent), B the second (sand), and every gap reads A minus B.
 */
import { useState } from 'react';
import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import ComparePanel from './ComparePanel.jsx';
import CompareDuelVerdict from './CompareDuelVerdict.jsx';
import CompareDuelChecks from './CompareDuelChecks.jsx';
import CompareDuelContribution from './CompareDuelContribution.jsx';
import CompareDuelExposure from './CompareDuelExposure.jsx';
import CompareDuelTrend from './CompareDuelTrend.jsx';
import CompareDuelPrincipleMap from './CompareDuelPrincipleMap.jsx';
import CompareDuelTable from './CompareDuelTable.jsx';
import { DUEL_SIDE } from '../duelTrendGeometry.js';
import { signed1 } from './compareDuelShared.jsx';

function Movement({ row, side }) {
  return (
    <span className="compare-duel-trendpanel__move">
      <span className={`compare-duel__swatch compare-duel__swatch--${side}`} aria-hidden="true" />
      {row.name}
      {row.delta != null && <b>{t('compare.duelTrendMove', { delta: signed1(row.delta) })}</b>}
    </span>
  );
}

function DuelTrendPanel({ duel }) {
  const { a, b, trend } = duel;
  return (
    <ComparePanel
      ariaLabel={t('compare.duelTrendAria')}
      header={t('compare.duelTrendHeader')}
      note={t('compare.duelTrendNote')}
      headExtra={(
        <span className="compare-duel-trendpanel__moves">
          <Movement row={a} side={DUEL_SIDE.A} />
          <Movement row={b} side={DUEL_SIDE.B} />
        </span>
      )}
    >
      {trend.a.length + trend.b.length >= 2 ? (
        <div className="compare-duel-trendpanel__body">
          <CompareDuelTrend a={trend.a} b={trend.b} aName={a.name} bName={b.name} />
        </div>
      ) : (
        <p className="compare-panel__fallback">{t('compare.duelTrendTooFew')}</p>
      )}
    </ComparePanel>
  );
}

function DuelBody({ duel, onOpenProject }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <>
      <CompareDuelVerdict duel={duel} onOpenProject={onOpenProject} />
      <CompareDuelChecks duel={duel} />
      <div className="compare-duel-pair">
        <CompareDuelContribution duel={duel} />
        <CompareDuelExposure duel={duel} />
      </div>
      <DuelTrendPanel duel={duel} />
      <CompareDuelPrincipleMap duel={duel} />
      <button type="button" className="compare-duel-tabletoggle" aria-expanded={showTable} onClick={() => setShowTable(!showTable)}>
        {showTable ? t('compare.duelTableHide') : t('compare.duelTableShow')}
      </button>
      {showTable && <CompareDuelTable duel={duel} />}
    </>
  );
}

export default function CompareDuelView({ duel, onOpenProject }) {
  const { a, b } = duel;
  return (
    <>
      <div className="term-page-top compare-page__top">
        {/* No local back button: the app breadcrumb already walks back,
            same as the dimension screen. */}
        <div className="compare-page__titles">
          <TermHeader
            name={t('compare.duelTitle')}
            sub={t('compare.duelSubtitle', { a: a.name, b: b.name, count: duel.sharedCount })}
          />
        </div>
      </div>
      {duel.ready ? <DuelBody duel={duel} onOpenProject={onOpenProject} /> : (
        <section className="compare-panel" aria-label={t('compare.duelAria')}>
          <p className="compare-panel__fallback">{t('compare.duelNeedsBoth')}</p>
        </section>
      )}
    </>
  );
}
