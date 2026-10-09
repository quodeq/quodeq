/**
 * Principle by principle: is the gap systematic or a few outliers? The
 * scatter shows every principle both projects scored; the lists name each
 * side's biggest edges and the weaknesses both share (both below good, and
 * close), the part no amount of comparing will fix. Lists and dots share a
 * hover highlight. Below MAP_MIN_POINTS the scatter is a lone dot, so only
 * the lists render.
 */
import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import ComparePanel from './ComparePanel.jsx';
import CompareDuelScatter from './CompareDuelScatter.jsx';
import { EVEN_BAND, MAP_MIN_POINTS, principleMap } from '../compareDuelAnalysis.js';
import { DUEL_SIDE } from '../duelTrendGeometry.js';
import { gapClass, SideScore, signed1 } from './compareDuelShared.jsx';

const WEAK = 'weak';

function PrincipleList({ title, kind, items, empty, aName, bName, hover, setHover }) {
  return (
    <div className={`compare-duel-map__list compare-duel-map__list--${kind}`}>
      <h3 className={`compare-duel-map__listHead compare-duel__ink--${kind}`}>{title}</h3>
      {items.length === 0 ? <p className="compare-duel-map__empty">{empty}</p> : (
        <ol className="compare-duel-map__rows">
          {items.map((p) => (
            <li
              key={p.id}
              className={`compare-duel-map__row${hover === p.id ? ' compare-duel-map__row--on' : ''}`}
              onMouseEnter={() => setHover(p.id)}
              onMouseLeave={() => setHover(null)}
            >
              <span className="compare-duel-map__what">
                {p.label} <span className="compare-duel-map__dim">{p.dimLabel}</span>
              </span>
              <span className="compare-duel-map__pair">
                <SideScore className={scoreColorClass(p.a)} project={aName} score={p.a} />
                <span aria-hidden="true">/</span>
                <SideScore className={scoreColorClass(p.b)} project={bName} score={p.b} />
              </span>
              {kind === WEAK ? <span /> : <span className={`compare-duel__gap ${gapClass(p.gap)}`}>{signed1(p.gap)}</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function CompareDuelPrincipleMap({ duel }) {
  const [hover, setHover] = useState(null);
  const { a, b } = duel;
  const map = principleMap(duel);
  if (!map.points.length) return null;
  const listProps = { aName: a.name, bName: b.name, hover, setHover };
  const showScatter = map.points.length >= MAP_MIN_POINTS;
  return (
    <ComparePanel
      ariaLabel={t('compare.duelMapAria')}
      header={t('compare.duelMapHeader', { count: map.points.length })}
      note={t('compare.duelMapNote', { a: a.name, b: b.name, aCount: map.counts.a, bCount: map.counts.b, even: map.counts.even, band: EVEN_BAND })}
    >
      <div className={`compare-duel-map${showScatter ? ' compare-duel-map--withScatter' : ''}`}>
        {showScatter && <CompareDuelScatter map={map} aName={a.name} bName={b.name} hover={hover} setHover={setHover} />}
        <div className="compare-duel-map__lists">
          <PrincipleList {...listProps} kind={DUEL_SIDE.A} title={t('compare.duelEdges', { name: a.name })} items={map.aEdges} empty={t('compare.duelEdgesNone')} />
          <PrincipleList {...listProps} kind={DUEL_SIDE.B} title={t('compare.duelEdges', { name: b.name })} items={map.bEdges} empty={t('compare.duelEdgesNone')} />
          <PrincipleList {...listProps} kind={WEAK} title={t('compare.duelShared')} items={map.shared} empty={t('compare.duelSharedNone')} />
        </div>
      </div>
    </ComparePanel>
  );
}
