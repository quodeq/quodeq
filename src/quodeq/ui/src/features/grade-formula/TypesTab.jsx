/**
 * The TYPES tab: every requirement type of the run with its severity, the
 * weight the draft gives it, its findings now and at the baseline, and
 * whether it is open or closed. Read-only: it explains weight and score.
 */
import { useMemo } from 'react';
import { groupRows, TYPE_GROUP } from '../violations/byTypeModel.js';
import TypeGroupRow from '../violations/components/TypeGroupRow.jsx';
import { t } from '../../strings/index.js';

const COLUMN_KEYS = ['gradeFormula.colType', 'gradeFormula.colSeverity', 'gradeFormula.colWeight',
  'gradeFormula.colFindings', 'gradeFormula.colBaseline', 'gradeFormula.colStatus'];

function TypeRow({ row }) {
  return (
    <tr className={row.closed ? 'heat-grid-type-row heat-grid-type-row--closed' : 'heat-grid-type-row'}>
      <td className="heat-grid-td-indent-2">
        <div className="heat-grid-file">
          <span className="type-row__code">{row.req}</span>
          {row.text && <span className="type-row__text">{row.text}</span>}
        </div>
      </td>
      <td>{row.severity ? <span className={`chip small sev-${row.severity}`}>{row.severity}</span> : null}</td>
      <td className="num">{row.weight}</td>
      <td className="num">{row.now}</td>
      <td className="num">{row.baseline === null ? <span className="heat-grid-td-muted">{t('gradeFormula.noBaseline')}</span> : row.baseline}</td>
      <td>{row.closed ? <span className="type-row__closed">{t('gradeFormula.typeClosed')}</span> : t('gradeFormula.typeOpen')}</td>
    </tr>
  );
}

function DimensionFilter({ dimensions, value, onChange }) {
  return (
    <select className="gf-picker" aria-label={t('gradeFormula.pickDimension')} value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">{t('gradeFormula.typesFilterAll')}</option>
      {dimensions.map((dim) => <option key={dim} value={dim}>{dim}</option>)}
    </select>
  );
}

/**
 * @param {Array} props.rows - typesRows() output
 * @param {string|null} props.dimensionFilter - one dimension, or null for all
 * @param {string[]} props.dimensions - the run's dimension names, for the filter
 */
export default function TypesTab({ rows, loading, dimensionFilter, setDimensionFilter, dimensions, noRun = false }) {
  const shown = useMemo(() => (dimensionFilter ? rows.filter((r) => r.dimension === dimensionFilter) : rows), [rows, dimensionFilter]);
  const grouped = useMemo(() => groupRows(shown), [shown]);
  if (noRun) return <p className="settings-description">{t('gradeFormula.typesNoRun')}</p>;
  return (
    <div className={`gf-types${loading ? ' section-pending' : ''}`}>
      <DimensionFilter dimensions={dimensions} value={dimensionFilter} onChange={setDimensionFilter} />
      {shown.length === 0 && !loading ? <p className="settings-description">{t('gradeFormula.typesEmpty')}</p> : (
        <div className="heat-grid-wrap heat-grid-wrap--flat">
          <table className="heat-grid heat-grid--flat heat-grid--types" aria-label={t('gradeFormula.typesAria')}>
            <thead>
              <tr>{COLUMN_KEYS.map((key, i) => <th key={key} className={i === 0 ? 'left' : undefined}>{t(key)}</th>)}</tr>
            </thead>
            <tbody>
              {grouped.map((entry) => (entry.type === TYPE_GROUP.TYPE
                ? <TypeRow key={entry.key} row={entry} />
                : <TypeGroupRow key={`${entry.type}-${entry.name}`} entry={entry} colSpan={COLUMN_KEYS.length - 1} />))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
