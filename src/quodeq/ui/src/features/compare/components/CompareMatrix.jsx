/**
 * CompareMatrix — a numbers-only score grid (the v4a pick): the fleet's
 * SCORE_MATRIX (projects x dimensions) and the dimension screen's
 * PRINCIPLE_MATRIX (projects x principles) share this one table.
 *
 * Scores wear grade colors and nothing else. Per column, the best score's
 * border turns solid-strong and the worst dashed. COLUMN HEADERS SORT
 * (desc, asc, back to the caller's order) and the lead rank renumbers with
 * the sort, so sorting by a column literally re-ranks the fleet. Hovering
 * a cell tints its row and column into a crosshair.
 *
 * Columns that don't fit the panel DISTRIBUTE instead of scrolling: see
 * useMatrixColumnChunks — the grid wraps into stacked column groups sized
 * to the container, each repeating the project lead (stripe, rank, name),
 * so everything stays on screen. Horizontal scroll remains only as a last
 * resort at widths where even the minimum group cannot fit.
 */
import { useState } from 'react';
import { scoreColorClass, scoreGradeColorVar } from '../../../utils/formatters.js';
import { SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import { OVERALL, computeMatrixExtremes, sortMatrixRows } from './compareMatrixModel.js';
import { useMatrixColumnChunks } from './useMatrixColumnChunks.js';
import CompareMatrixTable from './CompareMatrixTable.jsx';

const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

// Column headers hold 3-character numbers; full dimension or principle
// names would set the column width instead. The primary code is the same
// one the dimension tab bar already uses - the label's first 5 characters
// ("clean", "flexi", "maint") - so the matrix speaks the app's
// established vocabulary. When two columns share a prefix (the
// "independence from ..." principles), those fall back to a readable stem
// ("inde fra", "inde ui") so every header stays unique. Full names live
// in the tooltip and the sort button's aria-label.
const STOPWORDS = new Set(['from', 'of', 'the', 'and', 'for']);

const significantWords = (label) => String(label || '')
  .trim()
  .split(/[\s-]+/)
  .filter((w) => w && !STOPWORDS.has(w));

const prefixOf = (label) => String(label || '').trim().slice(0, 5);

function stemOf(label) {
  const words = significantWords(label);
  if (words.length <= 1) return (words[0] || '').slice(0, 5);
  return `${words[0].slice(0, 4)} ${words[words.length - 1].slice(0, 3)}`;
}

function makeShortLabels(columns) {
  const counts = new Map();
  for (const col of columns) {
    const code = prefixOf(col.label);
    counts.set(code, (counts.get(code) || 0) + 1);
  }
  const out = new Map();
  for (const col of columns) {
    const code = prefixOf(col.label);
    out.set(col.key, counts.get(code) > 1 ? stemOf(col.label) : code);
  }
  return out;
}

function makeHeaderCell(hoverClass, sort, toggleSort, sortMark) {
  return (key, label, title) => (
    <th
      key={key}
      className={`compare-matrix__num${hoverClass(key)}${sort?.key === key ? ' compare-matrix__sorted' : ''}`}
      title={title}
    >
      <button
        type="button"
        className="compare-matrix__colbtn"
        aria-label={t('compare.matrixSortAria', { column: title })}
        onClick={() => toggleSort(key)}
      >
        {label}{sortMark(key)}
      </button>
    </th>
  );
}

function leadCell(row, i) {
  return (
    <td className="compare-matrix__project">
      <span
        className="compare-matrix__stripe"
        style={{ background: scoreGradeColorVar(row.overall) }}
        aria-hidden="true"
      />
      <span className="compare-matrix__rank">{i + 1}</span>
      {row.onOpenRow ? (
        <button type="button" className="compare-matrix__rowbtn" onClick={row.onOpenRow}>
          {row.name}
        </button>
      ) : row.name}
      {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
    </td>
  );
}

function makeScoreCell(hoverClass, extremes, setHoverKey) {
  const ringClass = (colKey, score) => {
    const ex = extremes.get(colKey);
    if (!ex || score == null) return '';
    if (score === ex.min) return ' compare-matrix__cell--min';
    if (score === ex.max) return ' compare-matrix__cell--max';
    return '';
  };
  return (row, col) => {
    const cell = row.cells[col.key];
    if (cell?.score == null) {
      return (
        <td
          key={col.key}
          className={`compare-matrix__num compare-matrix__none${hoverClass(col.key)}`}
          onMouseEnter={() => setHoverKey(col.key)}
        >
          —
        </td>
      );
    }
    const cls = `${scoreColorClass(cell.score)}${ringClass(col.key, cell.score)}`;
    return (
      <td
        key={col.key}
        className={`compare-matrix__num${hoverClass(col.key)}`}
        onMouseEnter={() => setHoverKey(col.key)}
      >
        {cell.onClick ? (
          <button
            type="button"
            className={`compare-matrix__cell ${cls}`}
            title={cell.title}
            onClick={cell.onClick}
          >
            {score1(cell.score)}
          </button>
        ) : (
          <span className={`compare-matrix__cell ${cls}`}>{score1(cell.score)}</span>
        )}
      </td>
    );
  };
}

/**
 * @param {object} props
 * @param {string} props.ariaLabel
 * @param {string} props.header - Rendered inside the panel's SectionLabel.
 * @param {string} props.note - Right-hand explainer in the panel head.
 * @param {{key: string, label: string, avg: number|null}[]} props.columns
 * @param {{id: string, name: string, remote?: boolean, overall: number|null,
 *   onOpenRow?: Function,
 *   cells: Object<string, {score: number|null, onClick?: Function, title?: string}>}[]} props.matrixRows
 * @param {number|null} props.footOverall - Scope average for the overall column.
 */
/** Sort toggling + the hover-tint/header/score cell builders, bundled so
 * the component only owns state + render. */
function buildMatrixCellHelpers(sort, setSort, hoverKey, setHoverKey, extremes) {
  // desc -> asc -> back to the caller's order.
  const toggleSort = (key) => setSort((cur) => {
    if (cur?.key !== key) return { key, dir: 'desc' };
    if (cur.dir === 'desc') return { key, dir: 'asc' };
    return null;
  });
  const sortMark = (key) => {
    if (sort?.key !== key) return '';
    return sort.dir === 'desc' ? ' ↓' : ' ↑';
  };
  const hoverClass = (key) => (hoverKey === key ? ' compare-matrix__hovercol' : '');
  const headerCell = makeHeaderCell(hoverClass, sort, toggleSort, sortMark);
  const scoreCell = makeScoreCell(hoverClass, extremes, setHoverKey);
  return { hoverClass, headerCell, scoreCell };
}

export default function CompareMatrix({ ariaLabel, header, note, columns, matrixRows, footOverall }) {
  const [sort, setSort] = useState(null); // {key, dir: 'desc'|'asc'} | null
  const [hoverKey, setHoverKey] = useState(null);
  const { wrapRef, chunks } = useMatrixColumnChunks(columns, matrixRows.length >= 2 && columns.length >= 1);

  const displayRows = sortMatrixRows(matrixRows, sort);

  // Two projects make a comparison; a single column is still a grid worth
  // having (overall beside the one dimension the scope shares).
  if (matrixRows.length < 2 || columns.length < 1) return null;

  const shortLabels = makeShortLabels(columns);
  const extremes = computeMatrixExtremes(columns, matrixRows);
  const { hoverClass, headerCell, scoreCell } = buildMatrixCellHelpers(sort, setSort, hoverKey, setHoverKey, extremes);

  return (
    <section className="compare-panel" aria-label={ariaLabel}>
      <div className="compare-panel__head">
        <SectionLabel>{header}</SectionLabel>
        <span className="compare-panel__note">{note}</span>
      </div>
      <div className="compare-matrix" ref={wrapRef}>
        {chunks.map((chunkCols, ci) => (
          <CompareMatrixTable
            key={chunkCols[0]?.key ?? ci}
            chunkCols={chunkCols}
            ci={ci}
            displayRows={displayRows}
            shortLabels={shortLabels}
            headerCell={headerCell}
            leadCell={leadCell}
            scoreCell={scoreCell}
            footOverall={footOverall}
            hoverClass={hoverClass}
            setHoverKey={setHoverKey}
            OVERALL={OVERALL}
          />
        ))}
      </div>
    </section>
  );
}
