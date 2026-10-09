/**
 * Every score side by side, for lookup: dimensions sorted by the size of
 * their gap, each opening to its principles (one open at a time). Bars meet
 * in the middle; the gap reads left minus right.
 */
import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import ComparePanel from './ComparePanel.jsx';
import { DuelBars, gapClass, SideScore, signed1 } from './compareDuelShared.jsx';
import { DUEL_SIDE } from '../duelTrendGeometry.js';

const NO_GAP = '·';
const gapSize = (x) => (x.gap == null ? -1 : Math.abs(x.gap));
const byGap = (x, y) => gapSize(y) - gapSize(x);

function Cells({ row, aName, bName }) {
  return (
    <>
      <SideScore className={`compare-duel-table__score ${scoreColorClass(row.a)}`} project={aName} score={row.a} />
      <DuelBars a={row.a} b={row.b} />
      <SideScore className={`compare-duel-table__score ${scoreColorClass(row.b)}`} project={bName} score={row.b} />
      <span className={`compare-duel__gap ${gapClass(row.gap)}`}>{row.gap != null ? signed1(row.gap) : NO_GAP}</span>
    </>
  );
}

function DimensionGroup({ dim, items, open, onToggle, aName, bName }) {
  return (
    <li className="compare-duel-table__group">
      {items ? (
        <button type="button" className="compare-duel-table__row compare-duel-table__row--toggle" aria-expanded={open} onClick={onToggle}>
          <span className="compare-duel-table__label">
            <span className="compare-duel-table__chev" aria-hidden="true">{open ? '▾' : '▸'}</span>
            {dim.label}
          </span>
          <Cells row={dim} aName={aName} bName={bName} />
        </button>
      ) : (
        <div className="compare-duel-table__row">
          <span className="compare-duel-table__label">{dim.label}</span>
          <Cells row={dim} aName={aName} bName={bName} />
        </div>
      )}
      {open && items && (
        <ul className="compare-duel-table__principles">
          {[...items].sort(byGap).map((p) => (
            <li key={p.key} className="compare-duel-table__row compare-duel-table__row--sub">
              <span className="compare-duel-table__label">{p.label}</span>
              <Cells row={p} aName={aName} bName={bName} />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function CompareDuelTable({ duel }) {
  const { a, b } = duel;
  const dims = [...duel.dimensions].sort(byGap);
  const itemsByDim = new Map(duel.principles.map((g) => [g.key, g.items]));
  const [openKey, setOpenKey] = useState(dims.find((d) => itemsByDim.has(d.key))?.key ?? null);
  return (
    <ComparePanel ariaLabel={t('compare.duelTableAria')} header={t('compare.duelTableHeader')} note={t('compare.duelTableNote')}>
      <div className="compare-duel-table__cols" aria-hidden="true">
        <span>{t('compare.duelTableDimension')}</span>
        <span className={`compare-duel__name--${DUEL_SIDE.A}`}>{a.name}</span>
        <span />
        <span className={`compare-duel__name--${DUEL_SIDE.B}`}>{b.name}</span>
        <span>{t('compare.duelTableGap')}</span>
      </div>
      <ul className="compare-duel-table">
        {dims.map((d) => (
          <DimensionGroup
            key={d.key}
            dim={d}
            items={itemsByDim.get(d.key)}
            open={openKey === d.key}
            onToggle={() => setOpenKey(openKey === d.key ? null : d.key)}
            aName={a.name}
            bName={b.name}
          />
        ))}
      </ul>
    </ComparePanel>
  );
}
