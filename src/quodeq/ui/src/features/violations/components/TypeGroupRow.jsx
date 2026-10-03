import { TYPE_GROUP } from '../byTypeModel.js';
import { t } from '../../../strings/index.js';

/**
 * A dimension or principle header row of a grouped requirement-types table,
 * with its open and closed type counts.
 * @param {{type: string, name: string, openTypes: number, closedTypes: number}} props.entry
 * @param {number} props.colSpan - the columns after the first
 */
export default function TypeGroupRow({ entry, colSpan }) {
  const isDim = entry.type === TYPE_GROUP.DIMENSION;
  return (
    <tr className={isDim ? 'heat-grid-dim-row' : 'heat-grid-principle-row'}>
      <td className={isDim ? undefined : 'heat-grid-td-indent'}>{entry.name || t('violations.unknownPrinciple')}</td>
      <td colSpan={colSpan} className="heat-grid-td-muted">
        {t('violations.typeGroupCounts', { open: entry.openTypes, closed: entry.closedTypes })}
      </td>
    </tr>
  );
}
