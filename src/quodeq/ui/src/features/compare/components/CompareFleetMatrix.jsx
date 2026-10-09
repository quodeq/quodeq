/**
 * The score matrix: every project against every dimension, as a heatmap.
 * Tiles are tinted by grade; only the best (solid outline) and the worst
 * (dashed) of each dimension carry an outline, so they stand out. A header
 * ranks the rows by its column (again reverses); a tile opens that
 * project's own dimension screen (remote rows open the shared project).
 * Hovering a tile lights its row and column. Every dimension column has
 * the same width whatever its name's length (fixed table layout).
 */
import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { scoreColorClass, scoreGradeColorVar } from '../../../utils/formatters.js';
import ComparePanel from './ComparePanel.jsx';
import CompareSortButton from './CompareSortButton.jsx';
import { score1 } from '../compareFormatters.js';

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

function openCell(row, dim, onOpenProject, onOpenProjectDimension) {
  if (row.remote || !dim.fromRunId || !onOpenProjectDimension) return onOpenProject(row.id);
  return onOpenProjectDimension({ id: row.id, source: row.source, runId: dim.fromRunId, dimName: dim.name, dateLabel: dim.fromDateLabel });
}

function Tile({ dim, ext, onOpen, row }) {
  let mark = '';
  if (dim.score === ext.best) mark = ' compare-heat__tile--best';
  else if (dim.score === ext.worst) mark = ' compare-heat__tile--worst';
  return (
    <button
      type="button"
      className={`compare-heat__tile ${scoreColorClass(dim.score)}${mark}`}
      style={{ '--tile': scoreGradeColorVar(dim.score) }}
      title={t('compare.openDimensionIn', { dim: dim.label, project: row.name })}
      onClick={onOpen}
    >
      {score1(dim.score)}
    </button>
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

export default function CompareFleetMatrix({ rows, board, fleetScore, onOpenProject, onOpenProjectDimension }) {
  const [sort, setSort] = useState({ key: OVERALL, desc: true });
  const [hover, setHover] = useState(NO_HOVER);
  const ext = Object.fromEntries(board.map((b) => [b.key, extremes(rows, b.key)]));
  const colClass = (key) => (hover.col === key ? ' is-col' : '');
  const head = (key, label) => (
    <th key={key} scope="col" className={`compare-heat__head${colClass(key)}`}>
      <CompareSortButton sortKey={key} label={label} sort={sort} onSort={setSort} />
    </th>
  );
  return (
    <ComparePanel
      ariaLabel={t('compare.matrixAria')}
      header={t('compare.matrixHeader', { rows: rows.length, cols: board.length })}
      note={t('compare.matrixNoteFleet')}
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
          <tbody>
            {sortRows(rows, sort).map((row, i) => (
              <tr key={row.id} className={hover.row === row.id ? 'is-row' : undefined}>
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
                        <Tile dim={dim} ext={ext[b.key]} row={row} onOpen={() => openCell(row, dim, onOpenProject, onOpenProjectDimension)} />
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          <Foot board={board} rows={rows} fleetScore={fleetScore} hoverCol={hover.col} />
        </table>
      </div>
    </ComparePanel>
  );
}
