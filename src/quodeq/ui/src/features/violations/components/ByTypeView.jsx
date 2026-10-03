/**
 * The By type sub-tab: one row per requirement code with its baseline and
 * current counts, grouped by dimension and principle. Closed types stay
 * listed so a closed type is visible as a win, not a disappearance.
 */
import { useMemo } from 'react';
import TypeRowMenu from './TypeRowMenu.jsx';
import TypeGroupRow from './TypeGroupRow.jsx';
import { buildTypeRows, groupRows, TYPE_GROUP } from '../byTypeModel.js';
import { activationHandlers } from '../../../utils/a11y.js';
import { t } from '../../../strings/index.js';

const COLUMN_KEYS = ['violations.colType', 'violations.colBaseline', 'violations.colNow', 'violations.colDelta', 'violations.colStatus'];

function signed(n) {
  if (n === null || n === undefined) return '';
  return n > 0 ? `+${n}` : String(n);
}

function TypeName({ row, onTypeClick }) {
  const label = (
    <>
      <span className="type-row__code">{row.req}</span>
      {row.text && <span className="type-row__text">{row.text}</span>}
    </>
  );
  if (row.now === 0) return <div className="heat-grid-file">{label}</div>;
  return (
    <div
      className="heat-grid-file clickable" role="button" tabIndex={0}
      aria-label={t('violations.openTypeAria', { req: row.req })}
      {...activationHandlers(() => onTypeClick(row))}
    >
      {label}
    </div>
  );
}

function TypeRow({ row, onTypeClick, onDismissType }) {
  return (
    <tr className={row.closed ? 'heat-grid-type-row heat-grid-type-row--closed' : 'heat-grid-type-row'}>
      <td className="heat-grid-td-indent-2"><TypeName row={row} onTypeClick={onTypeClick} /></td>
      <td className="num">{row.baseline === null ? '-' : row.baseline}</td>
      <td className="num">{row.now}</td>
      <td className="num">{signed(row.delta)}</td>
      <td>
        {row.closed && <span className="type-row__closed">{t('violations.typeClosed')}</span>}
        {onDismissType && row.now > 0 && <TypeRowMenu row={row} onDismissType={onDismissType} />}
      </td>
    </tr>
  );
}

export default function ByTypeView({ dimensions, diffsByRun, standardsByDim, loading, onTypeClick, onDismissType }) {
  const rows = useMemo(() => buildTypeRows({ dimensions, diffsByRun, standardsByDim }), [dimensions, diffsByRun, standardsByDim]);
  const grouped = useMemo(() => groupRows(rows), [rows]);
  if (rows.length === 0 && !loading) return <p className="empty-state">{t('violations.noTypesFound')}</p>;
  return (
    <div className={`heat-grid-wrap heat-grid-wrap--flat${loading ? ' section-pending' : ''}`}>
      <table className="heat-grid heat-grid--flat heat-grid--types">
        <thead>
          <tr>{COLUMN_KEYS.map((key, i) => <th key={key} className={i === 0 ? 'left' : undefined}>{t(key)}</th>)}</tr>
        </thead>
        <tbody>
          {grouped.map((entry) => (entry.type === TYPE_GROUP.TYPE
            ? <TypeRow key={entry.key} row={entry} onTypeClick={onTypeClick} onDismissType={onDismissType} />
            : <TypeGroupRow key={`${entry.type}-${entry.name}`} entry={entry} colSpan={COLUMN_KEYS.length - 1} />))}
        </tbody>
      </table>
    </div>
  );
}
