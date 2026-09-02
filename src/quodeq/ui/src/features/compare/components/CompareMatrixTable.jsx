import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';

const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

/** One chunk's table: project lead column, an overall column on the first
 * chunk only, then that chunk's score columns — header, body and a
 * scope-average footer row. */
export default function CompareMatrixTable({
  chunkCols, ci, displayRows, shortLabels, headerCell, leadCell, scoreCell,
  footOverall, hoverClass, setHoverKey, OVERALL,
}) {
  return (
    <table onMouseLeave={() => setHoverKey(null)}>
      <thead>
        <tr>
          <th className="compare-matrix__project">{t('compare.colProject')}</th>
          {ci === 0 && headerCell(OVERALL, t('compare.matrixOverall'), t('compare.matrixOverall'))}
          {chunkCols.map((col) => headerCell(col.key, shortLabels.get(col.key), col.label))}
        </tr>
      </thead>
      <tbody>
        {displayRows.map((row, i) => (
          <tr key={row.id}>
            {leadCell(row, i)}
            {ci === 0 && (
              <td
                className={`compare-matrix__num compare-matrix__overall ${scoreColorClass(row.overall)}${hoverClass(OVERALL)}`}
                onMouseEnter={() => setHoverKey(OVERALL)}
              >
                {score1(row.overall)}
              </td>
            )}
            {chunkCols.map((col) => scoreCell(row, col))}
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td className="compare-matrix__project">{t('compare.scopeAverage')}</td>
          {ci === 0 && (
            <td className={`compare-matrix__num compare-matrix__overall ${scoreColorClass(footOverall)}`}>
              {score1(footOverall)}
            </td>
          )}
          {chunkCols.map((col) => (
            <td key={col.key} className={`compare-matrix__num ${scoreColorClass(col.avg)}${hoverClass(col.key)}`}>
              {score1(col.avg)}
            </td>
          ))}
        </tr>
      </tfoot>
    </table>
  );
}
