/**
 * A column header that ranks a table by its column: the first press sorts
 * best-first (↓), pressing the same header again reverses it (↑), another
 * header starts best-first again. Shared by the fleet's projects table and
 * score matrix so both sort with the same gesture.
 */
import { t } from '../../../strings/index.js';

const ARROW_DESC = ' ↓';
const ARROW_ASC = ' ↑';

/** The next sort state after pressing the header for `key`. */
export function nextSort(sort, key) {
  return sort.key === key ? { key, desc: !sort.desc } : { key, desc: true };
}

export default function CompareSortButton({ sortKey, label, sort, onSort, className = '' }) {
  const on = sort.key === sortKey;
  let arrow = '';
  if (on) arrow = sort.desc ? ARROW_DESC : ARROW_ASC;
  return (
    <button
      type="button"
      className={`compare-sortbtn${on ? ' compare-sortbtn--on' : ''} ${className}`}
      aria-pressed={on}
      aria-label={t('compare.matrixSortAria', { column: label })}
      onClick={() => onSort(nextSort(sort, sortKey))}
    >
      {label}{arrow}
    </button>
  );
}
