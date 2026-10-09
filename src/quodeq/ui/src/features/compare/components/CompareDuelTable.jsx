/**
 * Every score of both projects, always on screen, as a dot plot: each row
 * puts both scores on one shared, zoomed axis (grade zones behind it) and
 * joins them with a segment in the leading side's colour, so the segment's
 * length IS the gap. Aligned positions on a common scale are the most
 * accurately compared encoding; the old mirrored bars made the reader
 * compare two lengths on opposite sides of a seam.
 *
 * Above it, the one line a manager reads (who leads on how many dimensions,
 * the widest gap); in its head, sorting for the analyst and a switch
 * between dimensions only and dimensions with their principles.
 */
import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import ComparePanel from './ComparePanel.jsx';
import { gapClass, SideScore, signed1 } from './compareDuelShared.jsx';
import { DUEL_SIDE } from '../duelTrendGeometry.js';
import { TABLE_SORT, dimensionTally, scoreAxis, sortScoreRows } from '../compareDuelTable.js';

const NO_GAP = '·';

function leaderOf(row) {
  if (row.gap == null || row.gap === 0) return null;
  return row.gap > 0 ? DUEL_SIDE.A : DUEL_SIDE.B;
}

/* Both scores on the shared axis, joined by the gap segment. */
function Dumbbell({ row, axis }) {
  const lead = leaderOf(row);
  const pa = row.a != null ? axis.at(row.a) : null;
  const pb = row.b != null ? axis.at(row.b) : null;
  const both = pa != null && pb != null;
  return (
    <span className="compare-duel-plot" aria-hidden="true">
      {axis.zones.slice(1).map((z) => <span key={z.label} className="compare-duel-plot__zoneLine" style={{ left: `${axis.at(z.from)}%` }} />)}
      {both && (
        <span
          className={`compare-duel-plot__span${lead ? ` compare-duel-plot__span--${lead}` : ''}`}
          style={{ left: `${Math.min(pa, pb)}%`, width: `${Math.abs(pa - pb)}%` }}
        />
      )}
      {pb != null && <span className="compare-duel-plot__dot compare-duel-plot__dot--b" style={{ left: `${pb}%` }} />}
      {pa != null && <span className="compare-duel-plot__dot compare-duel-plot__dot--a" style={{ left: `${pa}%` }} />}
    </span>
  );
}

function Row({ row, axis, aName, bName, sub = false, toggle = null }) {
  const Label = toggle ? 'button' : 'span';
  return (
    <li className={`compare-duel-table__row${sub ? ' compare-duel-table__row--sub' : ''}`}>
      <Label
        className="compare-duel-table__label"
        {...(toggle ? { type: 'button', 'aria-expanded': toggle.open, onClick: toggle.onClick } : {})}
      >
        {toggle && <span className="compare-duel-table__chev" aria-hidden="true">{toggle.open ? '▾' : '▸'}</span>}
        {row.label}
      </Label>
      <SideScore className={`compare-duel-table__score ${scoreColorClass(row.a)}`} project={aName} score={row.a} />
      <Dumbbell row={row} axis={axis} />
      <SideScore className={`compare-duel-table__score compare-duel-table__score--b ${scoreColorClass(row.b)}`} project={bName} score={row.b} />
      <span className={`compare-duel__gap compare-duel-table__gap ${gapClass(row.gap)}`}>{row.gap != null ? signed1(row.gap) : NO_GAP}</span>
    </li>
  );
}

function AxisHead({ axis }) {
  return (
    <div className="compare-duel-table__axisRow" aria-hidden="true">
      <span>{t('compare.duelTableDimension')}</span>
      <span className="compare-duel-table__colName"><span className="compare-duel-plot__key compare-duel-plot__dot--a" /></span>
      <span className="compare-duel-table__axis">
        {axis.zones.map((z) => (
          <span key={z.label} className="compare-duel-table__zone" style={{ left: `${axis.at(z.from)}%`, width: `${axis.at(z.to) - axis.at(z.from)}%` }}>
            {z.label}
          </span>
        ))}
        {axis.ticks.map((v) => <span key={v} className="compare-duel-table__tick" style={{ left: `${axis.at(v)}%` }}>{v}</span>)}
      </span>
      <span className="compare-duel-table__colName"><span className="compare-duel-plot__key compare-duel-plot__dot--b" /></span>
      <span className="compare-duel-table__gapHead">{t('compare.duelTableGap')}</span>
    </div>
  );
}

function Summary({ duel }) {
  const tally = dimensionTally(duel);
  if (!tally.total) return null;
  return (
    <p className="compare-duel-table__summary">
      <span className="compare-duel-table__legend" aria-hidden="true">
        <span><span className="compare-duel-plot__key compare-duel-plot__dot--a" />{duel.a.name}</span>
        <span><span className="compare-duel-plot__key compare-duel-plot__dot--b" />{duel.b.name}</span>
      </span>
      {t('compare.duelTableTally', { a: duel.a.name, aCount: tally.a, b: duel.b.name, bCount: tally.b, even: tally.even, total: tally.total })}
      {tally.widest && (
        <span className="compare-duel-table__widest">
          {t('compare.duelTableWidest', { dimension: tally.widest.label })}
          <span className={`compare-duel__gap ${gapClass(tally.widest.gap)}`}>{signed1(tally.widest.gap)}</span>
        </span>
      )}
    </p>
  );
}

function Controls({ sort, setSort, withPrinciples, setWithPrinciples, aName, bName }) {
  const options = [
    [TABLE_SORT.GAP, t('compare.duelTableSortGap')],
    [TABLE_SORT.A, aName],
    [TABLE_SORT.B, bName],
    [TABLE_SORT.NAME, t('compare.duelTableSortName')],
  ];
  return (
    <span className="compare-duel-table__controls">
      <span className="compare-duel-table__seg" role="group" aria-label={t('compare.duelTableSortAria')}>
        <span className="compare-duel-table__segLabel">{t('compare.duelTableSort')}</span>
        {options.map(([key, label]) => (
          <button key={key} type="button" aria-pressed={sort === key} className="compare-duel-table__segBtn" onClick={() => setSort(key)}>{label}</button>
        ))}
      </span>
      <button type="button" aria-pressed={withPrinciples} className="compare-duel-table__segBtn compare-duel-table__principlesBtn" onClick={() => setWithPrinciples(!withPrinciples)}>
        {t('compare.duelTablePrinciples')}
      </button>
    </span>
  );
}

export default function CompareDuelTable({ duel }) {
  const { a, b } = duel;
  const [sort, setSort] = useState(TABLE_SORT.GAP);
  const [withPrinciples, setWithPrinciples] = useState(false);
  const [open, setOpen] = useState(() => new Set());
  const axis = scoreAxis(duel);
  const itemsByDim = new Map(duel.principles.map((g) => [g.key, g.items]));
  const toggleDim = (key) => setOpen((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const rowProps = { axis, aName: a.name, bName: b.name };
  return (
    <ComparePanel
      ariaLabel={t('compare.duelTableAria')}
      header={t('compare.duelTableHeader')}
      note={t('compare.duelTableNote')}
      headExtra={<Controls sort={sort} setSort={setSort} withPrinciples={withPrinciples} setWithPrinciples={setWithPrinciples} aName={a.name} bName={b.name} />}
    >
      <Summary duel={duel} />
      <AxisHead axis={axis} />
      <ul className="compare-duel-table">
        {sortScoreRows(duel.dimensions, sort).map((d) => {
          const items = itemsByDim.get(d.key);
          const shown = items && (withPrinciples || open.has(d.key));
          return (
            <li key={d.key} className="compare-duel-table__group">
              <ul className="compare-duel-table__rows">
                <Row row={d} {...rowProps} toggle={items && !withPrinciples ? { open: open.has(d.key), onClick: () => toggleDim(d.key) } : null} />
                {shown && sortScoreRows(items, sort).map((p) => <Row key={p.key} row={p} sub {...rowProps} />)}
              </ul>
            </li>
          );
        })}
      </ul>
    </ComparePanel>
  );
}
