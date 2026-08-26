/**
 * CompareMatrix — a numbers-only score grid (the v4a pick): the fleet's
 * SCORE_MATRIX (projects x dimensions) and the dimension screen's
 * PRINCIPLE_MATRIX appendix (projects x principles) share this one
 * presentational table.
 *
 * Scores wear grade colors and nothing else: no bars, no progress lines.
 * Each column rings its maximum (accent) and minimum (danger) so the
 * spread reads at a glance. Cells and column headers are navigation;
 * what a click opens is the caller's business (the fleet deep-links into
 * a project's dimension, the dimension screen into a project's principle).
 */
import { scoreColorClass } from '../../../utils/formatters.js';
import { SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';

const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

/**
 * @param {object} props
 * @param {string} props.ariaLabel
 * @param {string} props.header - Rendered inside the panel's SectionLabel.
 * @param {string} props.note - Right-hand explainer in the panel head.
 * @param {{key: string, label: string, avg: number|null, onOpen?: Function}[]} props.columns
 * @param {{id: string, name: string, remote?: boolean, overall: number|null,
 *   onOpenRow?: Function,
 *   cells: Object<string, {score: number|null, onClick?: Function, title?: string}>}[]} props.matrixRows
 * @param {number|null} props.footOverall - Scope average for the overall column.
 */
export default function CompareMatrix({ ariaLabel, header, note, columns, matrixRows, footOverall }) {
  // Two projects make a comparison; a single column is still a grid worth
  // having (overall beside the one dimension the scope shares).
  if (matrixRows.length < 2 || columns.length < 1) return null;

  // Per-column extremes for the rings. A column where every project holds
  // the same score has no spread to point at, so it gets no rings.
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

  return (
    <section className="compare-panel" aria-label={ariaLabel}>
      <div className="compare-panel__head">
        <SectionLabel>{header}</SectionLabel>
        <span className="compare-panel__note">{note}</span>
      </div>
      <div className="compare-matrix">
        <table>
          <thead>
            <tr>
              <th className="compare-matrix__project">{t('compare.colProject')}</th>
              <th className="compare-matrix__num">{t('compare.matrixOverall')}</th>
              {columns.map((col) => (
                <th key={col.key} className="compare-matrix__num" title={col.label}>
                  {col.onOpen ? (
                    <button type="button" className="compare-matrix__colbtn" onClick={col.onOpen}>
                      {col.label}
                    </button>
                  ) : (
                    <span className="compare-matrix__collabel">{col.label}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrixRows.map((row) => (
              <tr key={row.id}>
                <td className="compare-matrix__project">
                  {row.onOpenRow ? (
                    <button type="button" className="compare-matrix__rowbtn" onClick={row.onOpenRow}>
                      {row.name}
                    </button>
                  ) : row.name}
                  {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
                </td>
                <td className={`compare-matrix__num compare-matrix__overall ${scoreColorClass(row.overall)}`}>
                  {score1(row.overall)}
                </td>
                {columns.map((col) => {
                  const cell = row.cells[col.key];
                  if (cell?.score == null) {
                    return <td key={col.key} className="compare-matrix__num compare-matrix__none">—</td>;
                  }
                  const cls = `${scoreColorClass(cell.score)}${ringClass(col.key, cell.score)}`;
                  return (
                    <td key={col.key} className="compare-matrix__num">
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
                <td key={col.key} className={`compare-matrix__num ${scoreColorClass(col.avg)}`}>
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
