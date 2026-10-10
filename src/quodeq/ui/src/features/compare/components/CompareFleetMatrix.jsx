/**
 * The score matrix: every project against every dimension, a table of
 * numbers. Each score sits in a small square chip in its grade colour, like
 * the severity badges; the best of each dimension gets a strong outline and
 * the worst a dashed one, so they stand out against the quiet rest. A header
 * ranks the rows by its column (again reverses); a tile opens that
 * project's own dimension screen (remote rows open the shared project).
 * Hovering a tile lights its row and column. Every dimension column has
 * the same width whatever its name's length (fixed table layout).
 */
import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import ComparePanel from './ComparePanel.jsx';
import CompareSortButton from './CompareSortButton.jsx';
import { score1 } from '../compareFormatters.js';
import { openProjectDimension } from '../compareOpenDimension.js';

const OVERALL = 'overall';
const NONE = '·';
const NO_HOVER = Object.freeze({ row: null, col: null });

function extremes(rows, key) {
  const values = rows.map((r) => r.dims.find((d) => d.key === key)?.score).filter((v) => v != null);
  if (values.length < 2) return { best: null, worst: null };
  return { best: Math.max(...values), worst: Math.min(...values) };
}

function sortRows(rows, sort) {
  const value = (r) => (sort.key === OVERALL ? r.score : r.dims.find((d) => d.key === sort.key)?.score);
  const known = rows.filter((r) => value(r) != null).sort((a, b) => value(b) - value(a) || a.name.localeCompare(b.name));
  const unknown = rows.filter((r) => value(r) == null);
  return (sort.desc ? known : known.reverse()).concat(unknown);
}

function Tile({ dim, ext, onOpen, row }) {
  let mark = '';
  if (dim.score === ext.best) mark = ' compare-heat__tile--best';
  else if (dim.score === ext.worst) mark = ' compare-heat__tile--worst';
  return (
    <button
      type="button"
      className={`compare-heat__tile ${scoreColorClass(dim.score)}${mark}`}
      title={t('compare.openDimensionIn', { dim: dim.label, project: row.name })}
      onClick={onOpen}
    >
      {score1(dim.score)}
    </button>
  );
}

function MatrixBody({ rows, board, ext, colClass, hoverRow, setHover, openTile, onOpenProject }) {
  return (
    <tbody>
      {rows.map((row, i) => (
        <tr key={row.id} className={hoverRow === row.id ? 'is-row' : undefined}>
          <th scope="row" className="compare-heat__lead">
            <span className="compare-heat__rank">{i + 1}</span>
            <button type="button" className="compare-heat__name" title={row.name} onClick={() => onOpenProject(row.id)}>{row.name}</button>
            {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
          </th>
          <td className={`compare-heat__overall ${scoreColorClass(row.score)}${colClass(OVERALL)}`} onMouseEnter={() => setHover({ row: row.id, col: OVERALL })}>
            {score1(row.score)}
          </td>
          {board.map((b) => {
            const dim = row.dims.find((d) => d.key === b.key);
            return (
              <td key={b.key} className={`compare-heat__cell${colClass(b.key)}`} onMouseEnter={() => setHover({ row: row.id, col: b.key })}>
                {dim?.score == null ? <span className="compare-heat__none">{NONE}</span> : (
                  <Tile dim={dim} ext={ext[b.key]} row={row} onOpen={() => openTile(row, dim)} />
                )}
              </td>
            );
          })}
        </tr>
      ))}
    </tbody>
  );
}

function Foot({ board, rows, fleetScore, hoverCol }) {
  return (
    <tfoot>
      <tr>
        <th scope="row" className="compare-heat__lead">{t('compare.fleetAverage')}</th>
        <td className={`compare-heat__overall ${scoreColorClass(fleetScore)}`}>{score1(fleetScore)}</td>
        {board.map((b) => {
          const scored = rows.filter((r) => r.dims.some((d) => d.key === b.key && d.score != null)).length;
          return (
            <td key={b.key} className={`compare-heat__foot${hoverCol === b.key ? ' is-col' : ''}`}>
              <span className={scoreColorClass(b.avg)}>{score1(b.avg)}</span>
              <span className="compare-heat__scored">{t('compare.matrixScored', { scored, total: rows.length })}</span>
            </td>
          );
        })}
      </tr>
    </tfoot>
  );
}

/**
 * `ariaLabel`/`header`/`note` default to the fleet's. `onOpenCell(row, dim)`
 * overrides what a tile opens (the dimension drill-down opens principle
 * pages); `onHoverRow(id | null)` reports the hovered row to the page.
 */
export default function CompareFleetMatrix({
  rows, board, fleetScore, onOpenProject, onOpenProjectDimension,
  ariaLabel = null, header = null, note = null, onOpenCell = null, onHoverRow = null,
}) {
  const [sort, setSort] = useState({ key: OVERALL, desc: true });
  const [hover, setHoverState] = useState(NO_HOVER);
  const setHover = (h) => { setHoverState(h); onHoverRow?.(h.row); };
  const ext = Object.fromEntries(board.map((b) => [b.key, extremes(rows, b.key)]));
  const colClass = (key) => (hover.col === key ? ' is-col' : '');
  const head = (key, label) => (
    <th key={key} scope="col" className={`compare-heat__head${colClass(key)}`}>
      <CompareSortButton sortKey={key} label={label} sort={sort} onSort={setSort} />
    </th>
  );
  return (
    <ComparePanel
      ariaLabel={ariaLabel ?? t('compare.matrixAria')}
      header={header ?? t('compare.matrixHeader', { rows: rows.length, cols: board.length })}
      note={note ?? t('compare.matrixNoteFleet')}
    >
      <div className="compare-heat__scroll">
        <table className="compare-heat" onMouseLeave={() => setHover(NO_HOVER)}>
          <colgroup>
            <col className="compare-heat__colLead" />
            <col className="compare-heat__colOverall" />
            {board.map((b) => <col key={b.key} />)}
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className="compare-heat__lead">{t('compare.colProject')}</th>
              {head(OVERALL, t('compare.matrixOverall'))}
              {board.map((b) => head(b.key, b.label))}
            </tr>
          </thead>
          <MatrixBody
            rows={sortRows(rows, sort)} board={board} ext={ext} colClass={colClass} hoverRow={hover.row} setHover={setHover}
            openTile={(row, dim) => (onOpenCell ? onOpenCell(row, dim) : openProjectDimension(row, dim, onOpenProject, onOpenProjectDimension))}
            onOpenProject={onOpenProject}
          />
          <Foot board={board} rows={rows} fleetScore={fleetScore} hoverCol={hover.col} />
        </table>
      </div>
    </ComparePanel>
  );
}
