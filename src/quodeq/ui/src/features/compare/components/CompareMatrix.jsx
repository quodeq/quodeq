/**
 * CompareMatrix — a numbers-only score grid (the v4a pick): the fleet's
 * SCORE_MATRIX (projects x dimensions) and the dimension screen's
 * PRINCIPLE_MATRIX (projects x principles) share this one table.
 *
 * Scores wear grade colors and nothing else: no bars, no progress lines.
 * Per column, the best score's border turns solid-strong and the worst
 * dashed. Cells are navigation (what a click opens is the caller's
 * business); COLUMN HEADERS SORT — first click ranks the fleet by that
 * column best-first, a second flips it, a third restores the caller's
 * order. Hovering a cell tints its row and column into a crosshair, and
 * the project column stays sticky under horizontal scroll so numbers
 * never go anonymous.
 */
import { useMemo, useState } from 'react';
import { scoreColorClass, scoreGradeColorVar } from '../../../utils/formatters.js';
import { SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';

const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

const OVERALL = '__overall';

// Column headers hold 3-character numbers; full dimension or principle
// names would set the column width instead. Multi-word names compress to
// initials ("clean-architecture" -> "c-a", "independence from
// frameworks" -> "i-f"), single words to a 5-char stem ("maintainability"
// -> "maint"). When two columns' initials would collide, those fall back
// to readable stems ("inde fra") so every header stays unique. The full
// name lives in the tooltip and the sort button's aria-label.
const STOPWORDS = new Set(['from', 'of', 'the', 'and', 'for']);

const significantWords = (label) => String(label || '')
  .trim()
  .split(/[\s-]+/)
  .filter((w) => w && !STOPWORDS.has(w));

function initialsOf(label) {
  const words = significantWords(label);
  if (words.length <= 1) return (words[0] || '').slice(0, 5);
  return words.map((w) => w[0]).join('-');
}

function stemOf(label) {
  const words = significantWords(label);
  if (words.length <= 1) return (words[0] || '').slice(0, 5);
  return `${words[0].slice(0, 4)} ${words[words.length - 1].slice(0, 3)}`;
}

function makeShortLabels(columns) {
  const counts = new Map();
  for (const col of columns) {
    const code = initialsOf(col.label);
    counts.set(code, (counts.get(code) || 0) + 1);
  }
  const out = new Map();
  for (const col of columns) {
    const code = initialsOf(col.label);
    out.set(col.key, counts.get(code) > 1 ? stemOf(col.label) : code);
  }
  return out;
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
export default function CompareMatrix({ ariaLabel, header, note, columns, matrixRows, footOverall }) {
  const [sort, setSort] = useState(null); // {key, dir: 'desc'|'asc'} | null
  const [hoverKey, setHoverKey] = useState(null);

  const valueOf = (row, key) => (key === OVERALL ? row.overall : row.cells[key]?.score);

  const displayRows = useMemo(() => {
    if (!sort) return matrixRows;
    const dir = sort.dir === 'asc' ? 1 : -1;
    return matrixRows.slice().sort((a, b) => {
      const av = valueOf(a, sort.key);
      const bv = valueOf(b, sort.key);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av - bv) * dir;
    });
  }, [matrixRows, sort]);

  // Two projects make a comparison; a single column is still a grid worth
  // having (overall beside the one dimension the scope shares).
  if (matrixRows.length < 2 || columns.length < 1) return null;

  // Per-column extremes for the border treatment. A column where every
  // project holds the same score has no spread to point at.
  const extremes = new Map();
  for (const col of columns) {
    let min = Infinity;
    let max = -Infinity;
    for (const row of matrixRows) {
      const s = row.cells[col.key]?.score;
      if (s == null) continue;
      if (s < min) min = s;
      if (s > max) max = s;
    }
    if (min !== Infinity && min !== max) extremes.set(col.key, { min, max });
  }

  const ringClass = (colKey, score) => {
    const ex = extremes.get(colKey);
    if (!ex || score == null) return '';
    if (score === ex.min) return ' compare-matrix__cell--min';
    if (score === ex.max) return ' compare-matrix__cell--max';
    return '';
  };

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
  const shortLabels = makeShortLabels(columns);

  const headerCell = (key, label, title) => (
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

  return (
    <section className="compare-panel" aria-label={ariaLabel}>
      <div className="compare-panel__head">
        <SectionLabel>{header}</SectionLabel>
        <span className="compare-panel__note">{note}</span>
      </div>
      <div className="compare-matrix">
        <table onMouseLeave={() => setHoverKey(null)}>
          <thead>
            <tr>
              <th className="compare-matrix__project">{t('compare.colProject')}</th>
              {headerCell(OVERALL, t('compare.matrixOverall'), t('compare.matrixOverall'))}
              {columns.map((col) => headerCell(col.key, shortLabels.get(col.key), col.label))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr key={row.id}>
                <td className="compare-matrix__project">
                  {/* Same lead anatomy as the ranked table: grade stripe,
                      rank, name — and the rank follows the CURRENT order,
                      so sorting by a column literally re-ranks the fleet. */}
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
                <td
                  className={`compare-matrix__num compare-matrix__overall ${scoreColorClass(row.overall)}${hoverClass(OVERALL)}`}
                  onMouseEnter={() => setHoverKey(OVERALL)}
                >
                  {score1(row.overall)}
                </td>
                {columns.map((col) => {
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
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className="compare-matrix__project">{t('compare.scopeAverage')}</td>
              <td className={`compare-matrix__num compare-matrix__overall ${scoreColorClass(footOverall)}`}>
                {score1(footOverall)}
              </td>
              {columns.map((col) => (
                <td key={col.key} className={`compare-matrix__num ${scoreColorClass(col.avg)}${hoverClass(col.key)}`}>
                  {score1(col.avg)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}
